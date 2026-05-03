#!/usr/bin/env python3
"""SFT v1 trainer for Gemma 4 E4B-IT on Nepal-helpdesk task.

Recipe (locked):
- Base: google/gemma-4-E4B-it (BF16; we have 48 GB headroom)
- Method: rsLoRA r=64, α=128, target = q,k,v,o,gate,up,down (PLE frozen)
- Optimizer: AdamW 8-bit, LR 1e-4, cosine schedule, 100 warmup
- Data: corpora/sft_v1_train.jsonl (9076 items), val 477 items
- Epochs: up to 5 with save-best-by-val + early stopping
- Loss: assistant-only (user/system tokens masked at -100)

Robust to failure:
- Step 200: train loss must drop ≥5% (else abort)
- Step 500: val loss < 1.2× initial val loss (else abort)
- Step 1000: (removed for v3 — buggy gate, fired spuriously in both v1 and v2)
- Periodic val: save-best, early-stop on val divergence
- english_replay slice loss spike 2× initial → catastrophic forgetting → abort
- NaN/Inf/wall-clock kill switches
- Every abort path saves state to HF private repo + writes failure report

Usage:
    python scripts/train_sft_v1.py \
        --train corpora/sft_v1_train.jsonl \
        --val corpora/sft_v1_val.jsonl \
        --output runs/sft-v1-seed42 \
        --seed 42 \
        --hf-repo voidash/nepal-helpdesk-sft-v1-seed42 \
        --max-wall-hours 6
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---- Constants -------------------------------------------------------------

BASE_MODEL_ID = "google/gemma-4-E4B-it"
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


# ---- Auxiliary helpers -----------------------------------------------------


def _hf_token() -> str:
    """Pull HF token from ~/.fmw or env."""
    if t := os.environ.get("HF_TOKEN"):
        return t
    fmw = Path.home() / ".fmw"
    if fmw.exists():
        for line in fmw.read_text().splitlines():
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("HF_TOKEN not found in env or ~/.fmw")


def _load_chat_template_jinja(model_id: str, hf_token: str) -> str:
    """Per HF transformers issue #45205: Gemma 4's chat template ships as a
    separate jinja file, not in tokenizer_config.json. Download it ourselves."""
    from huggingface_hub import hf_hub_download

    path = hf_hub_download(
        repo_id=model_id,
        filename="chat_template.jinja",
        token=hf_token,
    )
    with open(path, encoding="utf-8") as f:
        return f.read()


def _set_seeds(seed: int) -> None:
    import torch

    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _unwrap_gemma4_clippable_linears(model) -> int:
    """Replace `Gemma4ClippableLinear` wrappers with their inner `nn.Linear`.

    Gemma 4 wraps every Linear with `Gemma4ClippableLinear` (a custom module
    that clips activations at inference for numerical stability). PEFT's LoRA
    injector only recognises stock `nn.Linear` / `nn.Embedding` / etc. and
    raises ValueError on the wrapper. We replace the wrapper in-place with
    its underlying `linear` attribute; the wrapped Linear keeps its weights,
    and the LoRA adapter is added to it normally.

    Returns the number of replacements made.
    """
    import torch.nn as nn

    n_replaced = 0
    # Snapshot the module list — we mutate during iteration, so capture first.
    for parent in list(model.modules()):
        for child_name, child in list(parent.named_children()):
            if type(child).__name__ == "Gemma4ClippableLinear":
                inner = getattr(child, "linear", None)
                if isinstance(inner, nn.Linear):
                    setattr(parent, child_name, inner)
                    n_replaced += 1
    return n_replaced


# ---- Dataset --------------------------------------------------------------


@dataclass
class TokenizedExample:
    input_ids: list[int]
    labels: list[int]  # -100 for prompt tokens, ids for assistant tokens
    attention_mask: list[int]
    source: str
    lang: str
    category: str


def _build_dataset(jsonl_path: Path, tokenizer, max_seq_length: int) -> list[TokenizedExample]:
    """Read messages-format JSONL → tokenized examples with assistant-only loss.

    For each record, we tokenize:
      1. messages without the final assistant content (prompt) → length P
      2. messages with the final assistant content (full) → length F
    Then labels[:P] = -100, labels[P:F] = full_ids[P:F].
    """
    out: list[TokenizedExample] = []
    skipped_too_long = 0
    skipped_no_assistant = 0

    with jsonl_path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            msgs: list[dict[str, str]] = r.get("messages") or []
            if not msgs or msgs[-1].get("role") != "assistant":
                skipped_no_assistant += 1
                continue

            # Prompt tokens: everything except the final assistant.
            # We format via chat template to TEXT first, then encode separately.
            # Calling apply_chat_template(tokenize=True) has version-dependent
            # return types (list[int] vs dict vs list[Encoding]) and breaks the
            # `prompt_ids is a strict prefix of full_ids` invariant we rely on.
            # Tokenizing text after formatting is robust across HF versions.
            prompt_msgs = msgs[:-1]
            try:
                prompt_text: str = tokenizer.apply_chat_template(
                    prompt_msgs,
                    tokenize=False,
                    add_generation_prompt=True,
                )
                full_text: str = tokenizer.apply_chat_template(
                    msgs,
                    tokenize=False,
                    add_generation_prompt=False,
                )
                # add_special_tokens=False because the chat template already
                # emits <bos> + turn markers in the text.
                prompt_ids: list[int] = tokenizer.encode(prompt_text, add_special_tokens=False)
                full_ids: list[int] = tokenizer.encode(full_text, add_special_tokens=False)
            except Exception as e:
                logging.warning("tokenize failed for %s: %s", r.get("id", "?"), e)
                continue

            if not full_ids or len(full_ids) <= len(prompt_ids):
                # Empty assistant content — skip
                skipped_no_assistant += 1
                continue

            if len(full_ids) > max_seq_length:
                # Try to truncate from the user side (keep the assistant intact)
                # since the assistant tokens are the only training signal.
                assistant_len = len(full_ids) - len(prompt_ids)
                room_for_prompt = max_seq_length - assistant_len
                if room_for_prompt < 64:
                    # Can't fit — skip
                    skipped_too_long += 1
                    continue
                # Truncate the prompt from the LEFT (preserve last messages)
                truncated_prompt = prompt_ids[-room_for_prompt:]
                full_ids = truncated_prompt + full_ids[len(prompt_ids):]
                prompt_ids = truncated_prompt

            labels = [-100] * len(prompt_ids) + list(full_ids[len(prompt_ids):])
            assert len(labels) == len(full_ids)
            attention = [1] * len(full_ids)

            out.append(
                TokenizedExample(
                    input_ids=full_ids,
                    labels=labels,
                    attention_mask=attention,
                    source=r.get("source") or "?",
                    lang=r.get("lang") or "?",
                    category=r.get("category") or "?",
                )
            )

    logging.info(
        "tokenized %s: %d kept, %d too_long, %d no_assistant",
        jsonl_path,
        len(out),
        skipped_too_long,
        skipped_no_assistant,
    )
    return out


def _collate_for_training(batch: list[TokenizedExample], pad_id: int) -> dict[str, Any]:
    import torch

    max_len = max(len(e.input_ids) for e in batch)
    bs = len(batch)
    input_ids = torch.full((bs, max_len), pad_id, dtype=torch.long)
    labels = torch.full((bs, max_len), -100, dtype=torch.long)
    attention = torch.zeros((bs, max_len), dtype=torch.long)
    for i, e in enumerate(batch):
        n = len(e.input_ids)
        input_ids[i, :n] = torch.tensor(e.input_ids, dtype=torch.long)
        labels[i, :n] = torch.tensor(e.labels, dtype=torch.long)
        attention[i, :n] = torch.tensor(e.attention_mask, dtype=torch.long)
    return {"input_ids": input_ids, "labels": labels, "attention_mask": attention}


# ---- Trainer state and callbacks ------------------------------------------


@dataclass
class RunState:
    """Mutable training state with kill-switch flags + history."""

    initial_train_loss: float | None = None
    initial_val_loss: float | None = None
    best_val_loss: float = float("inf")
    best_step: int = 0
    val_history: list[tuple[int, float]] = field(default_factory=list)  # (step, loss)
    per_slice_initial: dict[str, float] = field(default_factory=dict)
    per_slice_history: dict[str, list[tuple[int, float]]] = field(default_factory=lambda: defaultdict(list))

    abort_reason: str | None = None
    aborted_at_step: int | None = None
    start_wall: float = field(default_factory=time.time)


def _per_slice_val_loss(
    model, val_examples: list[TokenizedExample], pad_id: int, device, batch_size: int = 4
) -> dict[str, float]:
    """Compute per-slice mean cross-entropy on val set."""
    import torch

    model.eval()
    by_slice: dict[str, list[float]] = defaultdict(list)
    overall: list[float] = []

    with torch.no_grad():
        for i in range(0, len(val_examples), batch_size):
            batch = val_examples[i : i + batch_size]
            inputs = _collate_for_training(batch, pad_id)
            for k in inputs:
                inputs[k] = inputs[k].to(device)
            try:
                model_out = model(**inputs)
                # Per-example loss: refit by computing loss over labels manually.
                # HF returns single scalar loss averaged over all labels;
                # for per-slice, do it ourselves.
                logits = model_out.logits  # (bs, T, V)
                shift_logits = logits[:, :-1].contiguous()
                shift_labels = inputs["labels"][:, 1:].contiguous()
                # Per-token loss
                loss_fn = torch.nn.CrossEntropyLoss(reduction="none", ignore_index=-100)
                token_loss = loss_fn(
                    shift_logits.view(-1, shift_logits.size(-1)),
                    shift_labels.view(-1),
                ).view(shift_labels.size())  # (bs, T-1)
                mask = (shift_labels != -100).float()
                # Per-example mean over assistant tokens
                ex_loss = (token_loss * mask).sum(dim=1) / mask.sum(dim=1).clamp(min=1)
                for j, e in enumerate(batch):
                    by_slice[e.source].append(ex_loss[j].item())
                    overall.append(ex_loss[j].item())
            except Exception as e:
                logging.warning("val batch failed: %s", e)
                continue

    model.train()
    out: dict[str, float] = {"_overall": sum(overall) / max(1, len(overall))}
    for s, vs in by_slice.items():
        out[s] = sum(vs) / max(1, len(vs))
    return out


def _generate_one(model, tokenizer, messages: list[dict], max_new_tokens: int = 200) -> str:
    """Generate one completion from messages. Returns assistant text."""
    import torch

    model.eval()
    prompt_ids = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
    ).to(model.device)
    with torch.no_grad():
        out_ids = model.generate(
            prompt_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    new_ids = out_ids[0, prompt_ids.size(1):]
    text = tokenizer.decode(new_ids, skip_special_tokens=True)
    model.train()
    return text


def _push_to_hub(local_dir: Path, repo_id: str, hf_token: str, commit_msg: str) -> None:
    from huggingface_hub import HfApi

    api = HfApi(token=hf_token)
    api.create_repo(repo_id, repo_type="model", private=True, exist_ok=True)
    api.upload_folder(
        folder_path=str(local_dir),
        repo_id=repo_id,
        repo_type="model",
        commit_message=commit_msg,
    )


# ---- Final report writer --------------------------------------------------


def _write_failure_report(
    output_dir: Path,
    state: RunState,
    args: argparse.Namespace,
    extra: dict[str, Any] | None = None,
) -> None:
    report = {
        "status": "FAILED" if state.abort_reason else "INCOMPLETE",
        "abort_reason": state.abort_reason,
        "aborted_at_step": state.aborted_at_step,
        "best_val_loss": state.best_val_loss if state.best_val_loss != float("inf") else None,
        "best_step": state.best_step,
        "wall_seconds": round(time.time() - state.start_wall, 1),
        "val_history": state.val_history,
        "per_slice_history": dict(state.per_slice_history),
        "config": {
            "seed": args.seed,
            "epochs_target": args.epochs,
            "lr": args.lr,
            "lora_rank": args.lora_rank,
            "lora_alpha": args.lora_alpha,
            "use_rslora": args.use_rslora,
        },
        "extra": extra or {},
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "training_report.json").open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    md_lines = [
        f"# SFT v1 Training Report — {output_dir.name}",
        "",
        f"**Status**: {report['status']}",
    ]
    if state.abort_reason:
        md_lines.append(f"**Abort reason**: {state.abort_reason}")
        md_lines.append(f"**Aborted at step**: {state.aborted_at_step}")
    md_lines.extend([
        f"**Wall time**: {report['wall_seconds']:.0f}s",
        f"**Best val loss**: {report['best_val_loss']}",
        f"**Best step**: {state.best_step}",
        "",
        "## Config",
        f"- seed: {args.seed}",
        f"- LR: {args.lr}",
        f"- rsLoRA: r={args.lora_rank}, α={args.lora_alpha}, enabled={args.use_rslora}",
    ])
    with (output_dir / "training_report.md").open("w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


# ---- Main training loop ---------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", default="corpora/sft_v1_train.jsonl")
    ap.add_argument("--val", default="corpora/sft_v1_val.jsonl")
    ap.add_argument("--output", default="runs/sft-v1")
    ap.add_argument("--model-id", default=BASE_MODEL_ID)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--epochs", type=int, default=5)
    ap.add_argument("--per-device-batch", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--val-batch", type=int, default=2)
    ap.add_argument("--gradient-checkpointing", action="store_true", default=True)
    ap.add_argument("--no-gradient-checkpointing", dest="gradient_checkpointing", action="store_false")
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--warmup-steps", type=int, default=100)
    ap.add_argument("--lora-rank", type=int, default=64)
    ap.add_argument("--lora-alpha", type=int, default=128)
    ap.add_argument("--lora-dropout", type=float, default=0.05)
    ap.add_argument("--use-rslora", action="store_true", default=True)
    ap.add_argument("--no-rslora", dest="use_rslora", action="store_false")
    ap.add_argument("--max-seq-length", type=int, default=2048)
    ap.add_argument("--eval-every-steps", type=int, default=200)
    ap.add_argument("--save-every-steps", type=int, default=500)
    ap.add_argument("--push-every-steps", type=int, default=500)
    ap.add_argument(
        "--checkpoint-steps",
        default="",
        help="comma-separated list of step indices to save as step-N/ subdirs "
        "(in addition to best/). Codex v4 spec: '0,200,400,600,800,1000,1200,1400'. "
        "Each gets pushed to HF as a separate path so post-train selection can "
        "pick the actually-best by behavioral gate, not val loss alone.",
    )
    ap.add_argument("--max-wall-hours", type=float, default=6.0)
    ap.add_argument("--hf-repo", default=None, help="HF private repo to push to (e.g. voidash/nepal-helpdesk-sft-v1-seed42)")
    ap.add_argument("--max-val-examples", type=int, default=200, help="cap val for in-training eval speed")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    _set_seeds(args.seed)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Lazy imports — keep startup time low for failure detection.
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model

    hf_token = _hf_token()
    chat_template = _load_chat_template_jinja(args.model_id, hf_token)

    logging.info("loading tokenizer + model: %s", args.model_id)
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, token=hf_token)
    tokenizer.chat_template = chat_template
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id

    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        token=hf_token,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        attn_implementation="sdpa",
    )
    model.config.use_cache = False  # required for grad checkpointing later if needed

    # Gemma 4 wraps every Linear in a custom `Gemma4ClippableLinear` (inference-time
    # activation clipping for stability). PEFT only recognises stock `nn.Linear`
    # and refuses to inject LoRA into the wrapper. We replace the wrapper with
    # its inner `linear` before LoRA injection. We lose the clipping in those
    # layers — that's an inference-safety feature, not training-critical.
    n_unwrapped = _unwrap_gemma4_clippable_linears(model)
    if n_unwrapped:
        logging.info("unwrapped %d Gemma4ClippableLinear → nn.Linear for PEFT compatibility", n_unwrapped)

    logging.info("applying rsLoRA r=%d α=%d (rsLoRA=%s)", args.lora_rank, args.lora_alpha, args.use_rslora)
    lora_cfg = LoraConfig(
        r=args.lora_rank,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        target_modules=TARGET_MODULES,
        task_type="CAUSAL_LM",
        use_rslora=args.use_rslora,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    # Enable gradient checkpointing to halve activation memory.
    # `enable_input_require_grads()` is required when checkpointing+LoRA — the
    # LoRA layer's input must have requires_grad so gradients flow through the
    # checkpointed forward. Without it, the backward pass detaches and the
    # adapter never learns.
    if args.gradient_checkpointing:
        model.enable_input_require_grads()
        model.gradient_checkpointing_enable()
        logging.info("gradient checkpointing enabled")

    # Tokenize datasets
    train_examples = _build_dataset(Path(args.train), tokenizer, args.max_seq_length)
    val_examples = _build_dataset(Path(args.val), tokenizer, args.max_seq_length)
    if args.max_val_examples and len(val_examples) > args.max_val_examples:
        rng = random.Random(args.seed)
        val_examples = rng.sample(val_examples, args.max_val_examples)
    if not train_examples or not val_examples:
        logging.error("empty train or val")
        return 1

    pad_id = tokenizer.pad_token_id

    # Prep optimizer + scheduler
    try:
        import bitsandbytes as bnb

        optimizer = bnb.optim.AdamW8bit(
            (p for p in model.parameters() if p.requires_grad), lr=args.lr
        )
        logging.info("using AdamW 8-bit")
    except Exception as e:
        logging.warning("bnb AdamW8bit unavailable (%s); falling back to torch.optim.AdamW", e)
        optimizer = torch.optim.AdamW(
            (p for p in model.parameters() if p.requires_grad), lr=args.lr
        )

    grad_steps_per_epoch = max(1, len(train_examples) // (args.per_device_batch * args.grad_accum))
    total_grad_steps = grad_steps_per_epoch * args.epochs
    logging.info(
        "train_size=%d val_size=%d epochs=%d total_grad_steps≈%d",
        len(train_examples),
        len(val_examples),
        args.epochs,
        total_grad_steps,
    )

    from torch.optim.lr_scheduler import LambdaLR

    # Cosine with linear warmup
    def lr_lambda(step: int) -> float:
        if step < args.warmup_steps:
            return float(step) / max(1, args.warmup_steps)
        progress = (step - args.warmup_steps) / max(1, total_grad_steps - args.warmup_steps)
        progress = min(1.0, max(0.0, progress))
        # Cosine half-cycle 1.0 → 0.0
        import math
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    scheduler = LambdaLR(optimizer, lr_lambda)

    # State + training loop
    state = RunState()
    device = next(model.parameters()).device

    def _run_val() -> dict[str, float]:
        return _per_slice_val_loss(model, val_examples, pad_id, device, batch_size=args.val_batch)

    # Parse --checkpoint-steps once.
    explicit_ckpt_steps: set[int] = set()
    if args.checkpoint_steps:
        for tok in args.checkpoint_steps.split(","):
            tok = tok.strip()
            if tok:
                explicit_ckpt_steps.add(int(tok))

    def _write_state_json() -> None:
        with (output_dir / "state.json").open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "best_val_loss": state.best_val_loss,
                    "best_step": state.best_step,
                    "val_history": state.val_history,
                    "per_slice_history": dict(state.per_slice_history),
                    "abort_reason": state.abort_reason,
                    "aborted_at_step": state.aborted_at_step,
                    "explicit_ckpt_steps": sorted(explicit_ckpt_steps),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )

    def _save_to(subdir_name: str, reason: str) -> None:
        """Save model + tokenizer to output_dir/<subdir_name>/, write state.json,
        then optionally push to HF. Used by all checkpoint paths.
        """
        ckpt_dir = output_dir / subdir_name
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(str(ckpt_dir))
        tokenizer.save_pretrained(str(ckpt_dir))
        _write_state_json()
        if args.hf_repo:
            try:
                _push_to_hub(output_dir, args.hf_repo, hf_token, reason)
                logging.info("pushed to HF (%s): %s", subdir_name, args.hf_repo)
            except Exception as e:
                logging.warning("HF push failed for %s: %s", subdir_name, e)

    def _save_best_and_push(reason: str = "checkpoint") -> None:
        """Save the CURRENT model as the best/ checkpoint. Caller must have
        verified this is actually a new best — this function does NOT check.
        v3a regression: this function got called from periodic-push paths too,
        overwriting best/ with non-best weights. Now only call from new-best
        paths."""
        _save_to("best", reason)

    def _maybe_abort(reason: str, step: int) -> bool:
        state.abort_reason = reason
        state.aborted_at_step = step
        logging.error("ABORT @ step %d: %s", step, reason)
        try:
            _save_best_and_push(f"abort: {reason}")
        except Exception as e:
            logging.error("save-on-abort failed: %s", e)
        _write_failure_report(output_dir, state, args)
        return True

    # Initial val pass
    logging.info("computing initial val loss …")
    initial_val = _run_val()
    state.initial_val_loss = initial_val["_overall"]
    state.best_val_loss = state.initial_val_loss
    state.per_slice_initial = {k: v for k, v in initial_val.items() if not k.startswith("_")}
    state.val_history.append((0, state.initial_val_loss))
    for s, v in state.per_slice_initial.items():
        state.per_slice_history[s].append((0, v))
    logging.info("initial_val=%.4f per_slice=%s", state.initial_val_loss, state.per_slice_initial)

    # Training loop
    rng = random.Random(args.seed)
    global_step = 0
    micro_step = 0
    accum_loss = 0.0
    optimizer.zero_grad()

    try:
        for epoch in range(args.epochs):
            rng.shuffle(train_examples)
            for batch_start in range(0, len(train_examples), args.per_device_batch):
                if time.time() - state.start_wall > args.max_wall_hours * 3600:
                    if _maybe_abort(f"wall_time > {args.max_wall_hours}h", global_step):
                        return 2

                batch = train_examples[batch_start : batch_start + args.per_device_batch]
                if len(batch) < args.per_device_batch:
                    continue
                inputs = _collate_for_training(batch, pad_id)
                for k in inputs:
                    inputs[k] = inputs[k].to(device)
                try:
                    fwd_out = model(**inputs)
                    loss = fwd_out.loss / args.grad_accum
                except torch.cuda.OutOfMemoryError:
                    # OOM is fatal — can't recover mid-batch. Save & exit.
                    _maybe_abort("CUDA OOM during forward", global_step)
                    return 2
                if not torch.isfinite(loss):
                    _maybe_abort(f"non-finite loss: {loss.item()}", global_step)
                    return 2
                loss.backward()
                accum_loss += loss.item()
                micro_step += 1

                if micro_step % args.grad_accum == 0:
                    torch.nn.utils.clip_grad_norm_(
                        (p for p in model.parameters() if p.requires_grad), 1.0
                    )
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad()
                    global_step += 1
                    cur_train_loss = accum_loss
                    accum_loss = 0.0

                    if global_step == 1:
                        state.initial_train_loss = cur_train_loss

                    # ---- Kill-switch gates ----
                    if global_step == 200 and state.initial_train_loss is not None:
                        if cur_train_loss > state.initial_train_loss * 0.95:
                            if _maybe_abort(
                                f"train loss not decreased ≥5% by step 200 "
                                f"(initial={state.initial_train_loss:.4f} now={cur_train_loss:.4f})",
                                global_step,
                            ):
                                return 2

                    if global_step == 500:
                        # Quick val check
                        v = _run_val()
                        state.val_history.append((global_step, v["_overall"]))
                        for s, vv in v.items():
                            if not s.startswith("_"):
                                state.per_slice_history[s].append((global_step, vv))
                        logging.info(
                            "val @ step=%d overall=%.4f (initial=%.4f best_so_far=%.4f)",
                            global_step, v["_overall"], state.initial_val_loss, state.best_val_loss,
                        )
                        if v["_overall"] > state.initial_val_loss * 1.2:
                            if _maybe_abort(
                                f"val loss exploded by step 500 "
                                f"(initial={state.initial_val_loss:.4f} now={v['_overall']:.4f})",
                                global_step,
                            ):
                                return 2
                        if v["_overall"] < state.best_val_loss:
                            state.best_val_loss = v["_overall"]
                            state.best_step = global_step
                            _save_best_and_push("step500-best")

                    # NOTE: The step-1000 mini-generation gate was removed for v3.
                    # It fired spuriously in v1 (empty exception messages from
                    # buggy prompt_msgs_text reconstruction) AND in v2 (same
                    # bug, aborted at step 1000 in both runs). Best checkpoint
                    # was step ~500-600 in both, so the gate aborted training
                    # late enough to not lose the actual model — but it never
                    # produced a useful signal. Val loss tracking + per-slice
                    # loss tracking already catch divergence.

                    # ---- Periodic eval + save-best ----
                    if global_step % args.eval_every_steps == 0:
                        v = _run_val()
                        state.val_history.append((global_step, v["_overall"]))
                        for s, vv in v.items():
                            if not s.startswith("_"):
                                state.per_slice_history[s].append((global_step, vv))
                        # ALWAYS log val per-step. v3a regression: trainer only
                        # logged when a new best fired, so we couldn't see val
                        # trajectory in train_v3a.log without combing through
                        # state.json.
                        logging.info(
                            "val @ step=%d overall=%.4f (initial=%.4f best_so_far=%.4f best_step=%d)",
                            global_step, v["_overall"],
                            state.initial_val_loss, state.best_val_loss, state.best_step,
                        )
                        # English-replay catastrophic-forgetting check
                        if "english_replay" in state.per_slice_initial:
                            cur = v.get("english_replay")
                            init = state.per_slice_initial["english_replay"]
                            if cur is not None and cur > init * 2.0:
                                if _maybe_abort(
                                    f"english_replay loss spike: init={init:.3f} now={cur:.3f}",
                                    global_step,
                                ):
                                    return 2
                        # Save best ONLY when val actually improves.
                        if v["_overall"] < state.best_val_loss:
                            state.best_val_loss = v["_overall"]
                            state.best_step = global_step
                            _save_best_and_push("new-best")
                        # Early stop on val divergence (3 consecutive rises)
                        recent = [vh for (_, vh) in state.val_history[-3:]]
                        if (
                            len(recent) >= 3
                            and recent[0] > state.best_val_loss
                            and recent[1] > state.best_val_loss
                            and recent[2] > state.best_val_loss
                            and recent[2] > recent[1] > recent[0]
                        ):
                            logging.info("val rising 3 evals in a row; early stop with best")
                            state.abort_reason = "early_stop_val_divergence"
                            state.aborted_at_step = global_step
                            _write_failure_report(output_dir, state, args)
                            # Don't overwrite best/ on early-stop — best/ already
                            # holds the actual best from earlier.
                            return 0

                    # ---- Explicit checkpoint saves (codex v4 spec) ----
                    # Save AT each requested step into step-N/ subdir. Separate
                    # from best/ — these are for downstream selection by
                    # behavioral gate (run eval on each, pick the one that
                    # passes the most tests). Pushes the WHOLE output_dir to HF
                    # so step-N appears as a path in the repo.
                    if global_step in explicit_ckpt_steps:
                        _save_to(f"step{global_step}", f"checkpoint-step{global_step}")

                    # ---- Periodic push (without explicit checkpoint flag) ----
                    # When --checkpoint-steps is set, the step-N saves above
                    # provide crash-recovery snapshots. When it's NOT set, fall
                    # back to a periodic-push of best/ as a fail-safe.
                    elif global_step % args.push_every_steps == 0 and not explicit_ckpt_steps:
                        # Push the CURRENT state of best/ (whatever it last was)
                        # to HF as a crash-recovery snapshot. Doesn't OVERWRITE
                        # best/ with current weights — just re-uploads what's
                        # already on disk.
                        if args.hf_repo and (output_dir / "best").exists():
                            try:
                                _push_to_hub(output_dir, args.hf_repo, hf_token, f"periodic-step{global_step}")
                                logging.info("pushed periodic snapshot to HF: %s", args.hf_repo)
                            except Exception as e:
                                logging.warning("HF push failed: %s", e)

                    if global_step % 20 == 0:
                        logging.info(
                            "epoch=%d step=%d loss=%.4f lr=%.2e",
                            epoch,
                            global_step,
                            cur_train_loss,
                            scheduler.get_last_lr()[0],
                        )
    except KeyboardInterrupt:
        if _maybe_abort("KeyboardInterrupt", global_step):
            return 130
    except Exception as e:
        logging.error("training crashed: %s\n%s", e, traceback.format_exc())
        state.abort_reason = f"crash: {type(e).__name__}: {str(e)[:200]}"
        state.aborted_at_step = global_step
        try:
            # On crash, save current weights to crashed/ — do NOT overwrite
            # best/ which may hold an earlier good checkpoint. v3a regression:
            # we used to call _save_best_and_push here, which overwrote best/
            # with the crash-state weights.
            _save_to("crashed", state.abort_reason)
        except Exception:
            pass
        _write_failure_report(output_dir, state, args)
        return 3

    # Training complete (didn't early-stop, didn't crash)
    logging.info("training complete, %d steps total", global_step)
    # Final val — always log
    v = _run_val()
    state.val_history.append((global_step, v["_overall"]))
    logging.info(
        "FINAL val @ step=%d overall=%.4f (best=%.4f at step=%d)",
        global_step, v["_overall"], state.best_val_loss, state.best_step,
    )
    if v["_overall"] < state.best_val_loss:
        state.best_val_loss = v["_overall"]
        state.best_step = global_step
        _save_best_and_push("final-best")
    state.abort_reason = None
    # Save the LAST checkpoint to final/ — kept separately from best/ so
    # downstream selection (e.g. behavioral-gate eval per codex v4 spec)
    # can compare best-by-val vs last-step. v3a regression: we used to
    # overwrite best/ here unconditionally, losing the actual best.
    _save_to("final", "training-complete")
    _write_failure_report(output_dir, state, args, extra={"final_step": global_step})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
