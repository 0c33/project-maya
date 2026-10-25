#!/usr/bin/env python3
"""The fixed perplexity text for DeepSeek-V4.1 quant/engine comparisons: BOS + ~1.5k tokens of Python (bench/abbench.py,
written for this project, so not memorized) + ~1.5k tokens of English technical prose (REPORT.md, ditto), tokenized with
Xolotl's V4.1 tokenizer (joyai-llm pre-split, == HF tokenizers).  Writes data/ppl/ppl3k.ids (comma separated, one line)
and ppl3k.txt.  Run inside the image (needs `regex`):  python3 make_ppl_ids.py <tokenizer dir> <out dir>"""
import json, sys, pathlib
sys.path.insert(0, "/xsrc/tools")
import strata_tokenizer as ST
tdir, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
vocab = json.loads((tdir / "vocab.json").read_text(encoding="utf-8"))
tokens = [None] * len(vocab)
for t, i in vocab.items():
    tokens[i] = t
tok = ST.Tokenizer(tokens, (tdir / "merges.txt").read_text(encoding="utf-8").split("\n"),
                   json.loads((tdir / "token_type.json").read_text()), pre="joyai-llm")
code = pathlib.Path("/sab/bench/abbench.py").read_text()
prose = pathlib.Path("/sab/REPORT.md").read_text()
def take(text, n):
    ids = tok.encode(text)
    return ids[:n]
ids = [0] + take(code, 1500) + take("\n\n" + prose, 1500)
(out / "ppl3k.ids").write_text(",".join(map(str, ids)) + "\n")
(out / "ppl3k.txt").write_text(tok.decode(ids[1:]) if hasattr(tok, "decode") else "")
print(len(ids), "ids; first", ids[:8])
