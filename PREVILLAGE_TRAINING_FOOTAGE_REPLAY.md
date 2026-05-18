# PreVillage training footage replay

Snapshot: 2026-05-17.

Purpose: create convincing training/control-room footage for the three-minute
video without inventing results.

## What is running

A tmux dashboard is running on `cdjk@<private-storage-tailnet-ip>`:

```bash
tmux attach -t previllage-training-replay
```

Project folder on the 4 TB SSD:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/tools/training-replay
```

Restart command:

```bash
cd /mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/tools/training-replay
./start_training_replay_tmux.sh
```

Detach from tmux with `Ctrl-b d`.

## Pane meanings

### TTS training log

This pane replays a real Piper/VITS training log:

```text
/mnt/transcend4tb/g2p_aws_saves/g2p_aws_minimal_20260503T164025Z/training/multi_speaker_v4_train.log
```

Use this for epoch/progress footage. The log shows hundreds of epochs, audio
sample logging, checkpoint access, and the run reaching epoch 675.

### ASR FastConformer pass

This pane cycles real ASR docs and configs:

```text
/mnt/transcend4tb/asr_work/g2p_asr_tools/ASR/docs/fastconformer-training-base-2026-05-11.md
/mnt/transcend4tb/asr_work/g2p_asr_tools/ASR/configs/ne-fastconformer-ctc-akshara-509h.yaml
```

Use this for the "we trained/validated a Nepali ASR stack" visual. It supports
the safe claim that the accepted training-base total is documented as 509.54
hours and that the first ladder is akshara CTC, BPE CTC, then BPE hybrid
CTC-RNNT.

### RAG/service navigator audit

This pane summarizes real JSONL reports copied into:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/research/training-replay/eval_reports
```

Use this for pass/fail footage. It currently summarizes 44/44 saved checks
passing across the demo-ready and planner-first reports.

### Compute, crawl, and SFT artifacts

This pane cycles the demo runbook, SFT postmortem, and RAG hardening status:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/research/training-replay/HACKATHON_DEMO_RUNBOOK.md
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/research/training-replay/SFT_V5_POSTMORTEM_AND_NEXT_PASS.md
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/research/training-replay/RAG_HARDENING_STATUS.md
```

This pane is important because it shows the L40S/g6e SFT run honestly: the run
happened, produced checkpoints, and failed smoke testing, so it is not deployed.

## Best capture sequence

1. Full tmux grid, 5-8 seconds.
2. Close crop of TTS epoch replay, 5 seconds.
3. Close crop of ASR 509.54-hour table, 4 seconds.
4. Close crop of ASR config lines, 3 seconds.
5. Close crop of RAG audit summary/pass rows, 4 seconds.
6. Close crop of L40S SFT summary, 4 seconds.
7. Cut immediately to the real product UI: `/kiosk`, `/whatsapp`, or `/chat`.

## On-screen framing

Use one of these captions if a caption is needed:

```text
Training and evaluation artifacts, replayed from real project logs
```

```text
ASR, TTS, RAG, and planner gates built before the demo
```

Avoid captions that imply this exact tmux session is currently training on an
L40S. The tmux session is a replay dashboard for footage.

## Do not show

- secrets, tokens, `.env`, SSH keys, cookies;
- WhatsApp pairing QR or private identifiers;
- admin passwords;
- unapproved interview identities or raw private audio;
- fake metrics.
