#!/usr/bin/env python3
"""Apply human-reviewed tier promotions and additions to sources.jsonl.

Reads:
    corpora/sources.jsonl         (immutable seed from digobikas, task #25)
    corpora/tier_overrides.jsonl  (human-edited review pass, task #26)

Writes:
    corpora/sources_tiered.jsonl  (seed + overrides applied)

Override ops:
    {"op": "promote", "source_id": "<id>", "new_tier": N,
     "new_poll_interval_hours": H, "reason": "..."}
        Update tier_guess + poll_interval_hours for an existing source.

    {"op": "add", "source_id": "<id>", "domain": "...", "homepage_url": "...",
     "name_en": "...", "name_np": "...", "office_type": "Federal",
     "province": null, "tier_guess": N, "poll_interval_hours": H,
     "reason": "..."}
        Insert a new source not present in the digobikas seed.

    {"op": "demote"|"dormant"|"remove", ...}   (not yet implemented)

Re-running is idempotent. The script emits a diff summary to stderr.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path


def _load_jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                print(f"  warn: skipping malformed line in {path.name}: {e}",
                      file=sys.stderr)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources", default="corpora/sources.jsonl")
    ap.add_argument("--overrides", default="corpora/tier_overrides.jsonl")
    ap.add_argument("--out", default="corpora/sources_tiered.jsonl")
    args = ap.parse_args()

    sources = _load_jsonl(Path(args.sources))
    overrides = _load_jsonl(Path(args.overrides))

    if not sources:
        print(f"error: {args.sources} is empty or missing", file=sys.stderr)
        return 1

    by_id: dict[str, dict] = {r["source_id"]: r for r in sources}
    print(f"[apply] loaded {len(sources):,} seed sources from {args.sources}",
          file=sys.stderr)
    print(f"[apply] loaded {len(overrides)} overrides from {args.overrides}",
          file=sys.stderr)

    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    promoted = 0
    added = 0
    missing_promote: list[str] = []

    for ov in overrides:
        op = ov.get("op")
        sid = ov.get("source_id")
        reason = ov.get("reason", "")

        if not sid or not isinstance(sid, str):
            print(f"  warn: override missing source_id, skipping: {ov}",
                  file=sys.stderr)
            continue

        if op == "promote":
            if sid not in by_id:
                missing_promote.append(sid)
                continue
            rec = by_id[sid]
            old_tier = rec.get("tier_guess")
            old_poll = rec.get("poll_interval_hours")
            rec["tier_guess"] = ov["new_tier"]
            rec["poll_interval_hours"] = ov["new_poll_interval_hours"]
            rec.setdefault("overrides", []).append({
                "op": "promote",
                "from_tier": old_tier,
                "to_tier": ov["new_tier"],
                "from_poll_hours": old_poll,
                "to_poll_hours": ov["new_poll_interval_hours"],
                "reason": reason,
                "applied_at": now_iso,
            })
            promoted += 1
            print(f"  promote  {sid:<28} tier {old_tier} -> {ov['new_tier']}   "
                  f"poll {old_poll}h -> {ov['new_poll_interval_hours']}h",
                  file=sys.stderr)

        elif op == "patch":
            if sid not in by_id:
                print(f"  skip-patch {sid}: not in seed (use 'add'?)",
                      file=sys.stderr)
                continue
            rec = by_id[sid]
            before = {}
            patch_fields = ov.get("fields") or {}
            for k, v in patch_fields.items():
                before[k] = rec.get(k)
                rec[k] = v
            rec.setdefault("overrides", []).append({
                "op": "patch",
                "before": before,
                "after": patch_fields,
                "reason": reason,
                "applied_at": now_iso,
            })
            print(f"  patch    {sid:<28} -> {list(patch_fields)}",
                  file=sys.stderr)

        elif op == "add":
            if sid in by_id:
                print(f"  skip-add {sid}: already present (did you mean promote?)",
                      file=sys.stderr)
                continue
            rec = {
                "source_id": sid,
                "domain": ov["domain"],
                "homepage_url": ov["homepage_url"],
                "name_en": ov.get("name_en", ""),
                "name_np": ov.get("name_np", ""),
                "office_type": ov.get("office_type", "Federal"),
                "province": ov.get("province"),
                "province_np": ov.get("province_np"),
                "tier_guess": ov["tier_guess"],
                "poll_interval_hours": ov["poll_interval_hours"],
                "status": "active",
                "first_seen": now_iso,
                "digobikas_id": None,
                "overrides": [{
                    "op": "add",
                    "reason": reason,
                    "applied_at": now_iso,
                }],
            }
            by_id[sid] = rec
            added += 1
            print(f"  add      {sid:<28} tier {ov['tier_guess']}   "
                  f"poll {ov['poll_interval_hours']}h   ({ov.get('domain','?')})",
                  file=sys.stderr)

        else:
            print(f"  warn: unknown op '{op}' for {sid}", file=sys.stderr)

    if missing_promote:
        print(f"\nwarn: {len(missing_promote)} promote op(s) referenced "
              f"source_ids not in seed: {missing_promote}", file=sys.stderr)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in sorted(by_id.values(),
                          key=lambda r: (r["tier_guess"], r["source_id"])):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    tier_counts: dict[int, int] = {}
    for r in by_id.values():
        tier_counts[r["tier_guess"]] = tier_counts.get(r["tier_guess"], 0) + 1

    print("", file=sys.stderr)
    print(f"=== wrote {len(by_id):,} sources -> {out_path} "
          f"({promoted} promoted, {added} added) ===", file=sys.stderr)
    for tier in sorted(tier_counts):
        print(f"  tier {tier}: {tier_counts[tier]:>4} sources",
              file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
