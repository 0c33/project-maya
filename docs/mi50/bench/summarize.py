#!/usr/bin/env python3
"""Medians per tag / mode / prompt size from abbench's JSONL rows (results/<tag>.jsonl), plus agent pass counts
(results/agent-<tag>.jsonl). Usage: summarize.py <results dir> [tag ...] (default: every tag found)"""
import glob
import json
import os
import statistics
import sys

res = sys.argv[1]
tags = sys.argv[2:] or sorted({os.path.basename(p)[:-6] for p in glob.glob(f"{res}/*.jsonl")
                                if not os.path.basename(p).startswith("agent-")})
for tag in tags:
    p = f"{res}/{tag}.jsonl"
    if not os.path.exists(p):
        continue
    rows = [json.loads(l) for l in open(p)]
    print(f"== {tag}")
    for mode, key in (("decode", "decode_tps"), ("prefill", "prefill_tps"), ("prime", "prefill_tps")):
        for n in sorted({r["target"] for r in rows if r["mode"] == mode}, key=lambda x: (isinstance(x, str), str(x).zfill(8))):
            v = [r[key] for r in rows if r["mode"] == mode and r["target"] == n and r.get(key)]
            if not v:
                continue
            extra = ""
            if mode == "decode":
                toks = [r["completion_tokens"] for r in rows if r["mode"] == mode and r["target"] == n]
                extra = f"  (output tokens {min(toks)}-{max(toks)})"
            segs = {r.get("segments", 1) for r in rows if r["mode"] == mode and r["target"] == n}
            print(f"  {mode:7s} {n:>6}: median {statistics.median(v):7.2f}  runs {', '.join(f'{x:.2f}' for x in v)}"
                  f"{'  segments ' + str(sorted(segs)) if segs != {1} else ''}{extra}")
for p in sorted(glob.glob(f"{res}/agent-*.jsonl")):
    rows = [json.loads(l) for l in open(p)]
    print(f"== {os.path.basename(p)[:-6]}: {sum(r['pass'] for r in rows)}/{len(rows)} passed  " +
          "  ".join(f"{r['task']}={'PASS' if r['pass'] else 'FAIL'}({r['seconds']}s)" for r in rows))
