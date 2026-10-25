#!/usr/bin/env python3
"""Engine-agnostic A/B bench over the OpenAI chat API: the same requests to vLLM and to Strata.

  abbench.py <url> <model> <tag> decode  <N> [<N> ...]   decode t/s after the fixed N-token prompt (prompts/pN.json)
  abbench.py <url> <model> <tag> prefill <N> [<N> ...]   cold prefill t/s on the N-token prompt
Env: REPS (3), MAX_TOKENS (256), COOL_C (55), ABORT_C (80), OUT (results dir), SEG (1).

decode: one priming request (max_tokens 1) puts the prompt in the engine's prompt/prefix cache, then REPS streamed
requests on the same prompt: decode t/s = (completion_tokens - 1) / (t_last_delta - t_first_delta), from the client's
chunk timestamps (no engine metrics, so both engines are measured alike; MTP drafts arrive in bursts, which this
averages over). The prompt asks for a long answer: Strata has no ignore_eos, so the output length is the model's,
capped at MAX_TOKENS, and every row records it.
prefill: a unique nonce first (no prefix-cache hit on either engine), max_tokens 1, streamed: prefill t/s =
prompt_tokens / TTFT. Thinking off (chat_template_kwargs.enable_thinking=false), greedy.
SEG_CHARS=n: segments of at most ~n characters instead (code is ~3.6 chars/token).
SEG=k (thermal: a long read at a fixed power cap can pass the 80 C watchdog) reads a prompt as k growing prefixes
(cut at line ends at 1/k, 2/k, ...; the last one is the whole prompt), cooling to COOL_C between them: the engine's
prefix/prompt cache keeps what was read, so each request reads only the new part at its real depth. The prefill rate
is then prompt_tokens / (sum of the segments' TTFTs); each segment is its own JSON line (mode "seg"), and the engine
log shows how much each one reused. Used for the priming read of decode runs and for prefill runs alike.
Every request: one JSON line in OUT/<tag>.jsonl; sensors (power, cap, sclk, edge/junction/HBM per card) every second in
OUT/<tag>.sensors.csv. Any sensor >= ABORT_C (or unreadable) aborts; run under gpu-tune/safe-run.sh as well.
"""
import glob
import hashlib
import json
import os
import sys
import threading
import time
import urllib.request
import uuid

URL, MODEL, TAG, MODE = sys.argv[1].rstrip("/"), sys.argv[2], sys.argv[3], sys.argv[4]
LENGTHS = [int(x) if x.isdigit() else x for x in sys.argv[5:]]   # a name = prompts/p<name>.json (codegen, codeedit)
REPS = int(os.environ.get("REPS", "3"))
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "256"))
COOL_C = float(os.environ.get("COOL_C", "55"))
SEG = int(os.environ.get("SEG", "1"))
# SEG_API=completions: the segments before the last go to /v1/completions as raw, hand-templated text (vLLM: a cut
# inside one chat message is not a point where the hybrid model's recurrent state is cached, the end of a request is,
# so each segment must be an exact token prefix of the next). TEMPLATE renders the user turn as the server's chat
# template does with thinking off (checked against vLLM's /tokenize before a run: tmpl_check.py).
SEG_API = os.environ.get("SEG_API", "chat")
TEMPLATE_HEAD = "<|im_start|>user\n"
ABORT_C = float(os.environ.get("ABORT_C", "80"))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("OUT", os.path.join(HERE, "..", "results"))
os.makedirs(OUT, exist_ok=True)
CARDS = sorted(glob.glob("/sys/class/drm/card[01]/device/hwmon/hwmon*"))
rows = open(os.path.join(OUT, f"{TAG}.jsonl"), "a", buffering=1)
sens = open(os.path.join(OUT, f"{TAG}.sensors.csv"), "a", buffering=1)
step = {"name": "idle"}
peak = {}


def rd(p, div):
    return int(open(p).read()) / div


def sensors():
    return [[rd(f"{h}/power1_input", 1e6), rd(f"{h}/power1_cap", 1e6), rd(f"{h}/freq1_input", 1e6),
             rd(f"{h}/temp1_input", 1e3), rd(f"{h}/temp2_input", 1e3), rd(f"{h}/temp3_input", 1e3)] for h in CARDS]


def logger():
    if sens.tell() == 0:
        sens.write("t,tag,step,card,power_w,cap_w,sclk_mhz,edge_c,junction_c,mem_c\n")
    while True:
        now = time.time()
        try:
            vals = sensors()
        except OSError as e:
            print(f"ABORT: sensor unreadable ({e})", flush=True)
            os._exit(3)
        for h, v in zip(CARDS, vals):
            sens.write(f"{now:.1f},{TAG},{step['name']},{h.split('/')[4]}," + ",".join(f"{x:.0f}" for x in v) + "\n")
            peak["junction"] = max(peak.get("junction", 0), v[4])
            peak["mem"] = max(peak.get("mem", 0), v[5])
            peak["power"] = max(peak.get("power", 0), v[0])
            peak["cap"] = v[1]
            if max(v[3:]) >= ABORT_C:
                print(f"ABORT: {h.split('/')[4]} sensor at {max(v[3:]):.0f} C", flush=True)
                os._exit(3)
        time.sleep(max(0.0, 1 - (time.time() - now)))


def cool():
    t0 = time.time()
    while max(max(v[3:]) for v in sensors()) >= COOL_C:
        time.sleep(2)
    if time.time() - t0 > 1:
        print(f"   (cooled to < {COOL_C:.0f} C in {time.time() - t0:.0f} s)", flush=True)


def complete_raw(prompt):
    """/v1/completions with a raw prompt, max_tokens 1, streamed: the segment read of SEG_API=completions."""
    body = {"model": MODEL, "prompt": prompt, "max_tokens": 1, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}}
    req = urllib.request.Request(f"{URL}/v1/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    first, usage = None, {}
    with urllib.request.urlopen(req, timeout=7200) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line[5:].strip() == "[DONE]":
                continue
            ev = json.loads(line[5:].strip())
            if ev.get("usage"):
                usage = ev["usage"]
            if any(ch.get("text") for ch in ev.get("choices") or []):
                first = first or time.time()
    return {"t_send": t0, "ttft": (first or time.time()) - t0, "t_first": first, "t_last": first,
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "finish": None, "head": ""}


def chat(text, max_tokens):
    body = {"model": MODEL, "messages": [{"role": "user", "content": text}], "max_tokens": max_tokens,
            "temperature": 0, "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False}}
    if PP != "none":   # explicit greedy: Strata's server otherwise adds the model card's presence_penalty 1.5 (see PP)
        body["presence_penalty"] = float(PP)
    req = urllib.request.Request(f"{URL}/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    first = last = None
    usage, finish, head, full = {}, None, "", []
    with urllib.request.urlopen(req, timeout=7200) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            ev = json.loads(data)
            if ev.get("usage"):
                usage = ev["usage"]
            for ch in ev.get("choices") or []:
                d = ch.get("delta") or {}
                piece = (d.get("content") or "") + (d.get("reasoning_content") or d.get("reasoning") or "")
                if piece:
                    now = time.time()
                    first = first or now
                    last = now
                    if len(head) < 160:
                        head += piece
                    full.append(piece)
                finish = ch.get("finish_reason") or finish
    text = "".join(full)   # text_sha: the whole greedy answer's hash, to compare arms' outputs (identical text or not)
    return {"t_send": t0, "ttft": (first - t0) if first else None, "t_first": first, "t_last": last,
            "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
            "finish": finish, "head": head[:160], "text_sha": hashlib.sha1(text.encode()).hexdigest()[:12],
            "tail": text[-120:]}


def record(kind, n, rep, r):
    row = {"tag": TAG, "mode": kind, "target": n, "rep": rep, **r}
    ct = r.get("completion_tokens") or 0
    if kind == "decode" and ct > 1 and r["t_last"] > r["t_first"]:
        row["decode_tps"] = (ct - 1) / (r["t_last"] - r["t_first"])
    if kind in ("prefill", "prime") and r["ttft"] and r["prompt_tokens"]:
        row["prefill_tps"] = r["prompt_tokens"] / r["ttft"]
    return row


SEG_CHARS = int(os.environ.get("SEG_CHARS", "0"))
# PP: the presence_penalty every chat request sends (default 0 = plain greedy on every engine).  Strata's server fills a
# missing one from the model card (Qwen3.8 instruct: 1.5), which also turns its --pipeline-windows decode off
# ("a request with repetition penalties (penalty_last_n) decodes serially"); PP=none leaves the field out (the server's
# default, as in the runs before 2026-10-22 09:10)
PP = os.environ.get("PP", "0")
WARMUP = int(os.environ.get("WARMUP", "0"))   # decode mode: tokens of one discarded request before the reps (0 = none)


def stable_cut(text, target, lo):
    """The line end nearest below target (else above), not at or before lo, after which the prefix tokenizes as in the
    whole prompt: the next line is not blank or whitespace-only (Qwen's pre-split joins "\n" with following blank
    lines into one piece; indentation is split off on its own).  -1 if none."""
    def ok(c):
        nxt = text.find("\n", c + 1)
        line = text[c + 1: nxt if nxt >= 0 else len(text)]
        return text[c + 1] not in "\r\n" and line.strip() != ""
    c = text.rfind("\n", lo + 1, target + 1)
    while c > lo and not ok(c):
        c = text.rfind("\n", lo + 1, c)
    if c > lo:
        return c
    c = text.find("\n", target)
    while 0 < c < len(text) - 1 and not ok(c):
        c = text.find("\n", c + 1)
    return c if 0 < c < len(text) - 1 else -1


def segments(text):
    """Growing prefixes of text, cut at stable line ends: SEG of them evenly, or (SEG_CHARS) one every ~SEG_CHARS
    characters (a bound on the tokens one request reads at once); the last one is text itself."""
    cuts, last = [], 0
    step = SEG_CHARS if SEG_CHARS else (len(text) // SEG if SEG > 1 else 0)
    while step and last + step < len(text) - step // 4:
        c = stable_cut(text, last + step, last)
        if c < 0:
            break
        cuts.append(text[:c + 1])
        last = c + 1
    return cuts + [text]


def read_prompt(kind, n, rep, text):
    """Read text with max_tokens 1 (in SEG segments when SEG > 1); returns (sum of TTFTs, last response, rows)."""
    total, out = 0.0, []
    parts = segments(text)
    for i, part in enumerate(parts):
        if i:
            cool()
        step["name"] = f"{kind}{n}_{rep}" + (f"_s{i}" if len(parts) > 1 else "")
        peak.clear()
        if SEG_API == "completions" and i < len(parts) - 1:
            r = complete_raw(TEMPLATE_HEAD + part)
        else:
            r = chat(part, 1)
        total += r["ttft"]
        row = record("seg" if len(parts) > 1 else kind, n, rep, r)
        row["peak"] = dict(peak)
        if len(parts) > 1:
            row["seg"] = f"{i + 1}/{len(parts)}"
            print(f"      seg {i + 1}/{len(parts)}: prompt {r['prompt_tokens']} tok, TTFT {r['ttft']:.2f} s, junction max "
                  f"{peak.get('junction', 0):.0f} C", flush=True)
        out.append(row)
    return total, r, out


threading.Thread(target=logger, daemon=True).start()
print(f"[{TAG}] {MODE} {LENGTHS} on {URL} ({MODEL}), reps {REPS}, max_tokens {MAX_TOKENS}", flush=True)
for n in LENGTHS:
    text = json.load(open(os.path.join(HERE, "prompts", f"p{n}.json")))["text"]
    if MODE == "decode":
        cool()
        total, r, segrows = read_prompt("prime", n, 0, text)
        for row in segrows[:-1]:
            rows.write(json.dumps(row) + "\n")
        row = segrows[-1] | {"mode": "prime", "ttft_sum": total, "segments": len(segrows),
                             "prefill_tps": (r["prompt_tokens"] or 0) / total if total else None}
        rows.write(json.dumps(row) + "\n")
        print(f"  {n:>6} prime: prompt {r['prompt_tokens']} tok, read {total:.2f} s in {len(segrows)} segment(s) "
              f"({row.get('prefill_tps') or 0:.0f} tok/s)  junction max {row['peak'].get('junction', 0):.0f} C", flush=True)
        if WARMUP > 0:   # a discarded request first: the expert cache adapts to the workload before the measured reps
            cool()
            step["name"] = f"warm{n}"
            w = chat(text, WARMUP)
            print(f"  {n:>6} warm-up: {w['completion_tokens']} tok (not recorded)", flush=True)
        for rep in range(REPS):
            cool()
            step["name"] = f"dec{n}_{rep}"
            peak.clear()
            r = chat(text, MAX_TOKENS)
            row = record("decode", n, rep, r)
            row["peak"] = dict(peak)
            rows.write(json.dumps(row) + "\n")
            print(f"  {n:>6} rep{rep}: TTFT {r['ttft']:.2f} s, {r['completion_tokens']} tok ({r['finish']}), "
                  f"decode {row.get('decode_tps', 0):.2f} t/s  power max {peak.get('power', 0):.0f} W (cap "
                  f"{peak.get('cap', 0):.0f})  junction max {peak.get('junction', 0):.0f} C", flush=True)
    elif MODE == "prefill":
        for rep in range(REPS):
            cool()
            total, r, segrows = read_prompt("pf", n, rep, f"Request {uuid.uuid4()}\n\n" + text)
            for row in segrows[:-1]:
                rows.write(json.dumps(row) + "\n")
            row = segrows[-1] | {"mode": "prefill", "ttft_sum": total, "segments": len(segrows),
                                 "prefill_tps": (r["prompt_tokens"] or 0) / total if total else None}
            rows.write(json.dumps(row) + "\n")
            print(f"  {n:>6} cold rep{rep}: prompt {r['prompt_tokens']} tok, read {total:.2f} s in {len(segrows)} "
                  f"segment(s) -> {row.get('prefill_tps') or 0:.1f} tok/s  power max {row['peak'].get('power', 0):.0f} W "
                  f"(cap {row['peak'].get('cap', 0):.0f})  junction max {row['peak'].get('junction', 0):.0f} C", flush=True)
    step["name"] = "idle"
print(f"[{TAG}] done", flush=True)
