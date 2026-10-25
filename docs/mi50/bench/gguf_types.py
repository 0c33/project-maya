#!/usr/bin/env python3
"""Tensor-type summary of GGUF shards (headers only): bytes per type for routed experts vs everything else.
   python3 -I gguf_types.py <maya pack_gguf.py dir> <gguf>..."""
import sys, collections, importlib.util
spec = importlib.util.spec_from_file_location("pg", sys.argv[1] + "/pack_gguf.py")
pg = importlib.util.module_from_spec(spec); spec.loader.exec_module(pg)
agg = collections.defaultdict(lambda: [0, 0])
for path in sys.argv[2:]:
    import pathlib
    g = pg.Gguf(pathlib.Path(path))
    for t in g.tensors:
        name, ttype = t[0], t[1]
        dims = t[2] if len(t) > 2 else ()
        n = 1
        for d in dims: n *= int(d)
        tn, blk, bb = pg.TYPES.get(ttype, (str(ttype), 1, 0))
        nb = n // blk * bb if bb else 0
        kind = "expert" if "_exps" in name else ("engram" if "engram" in name else "dense")
        agg[(kind, tn)][0] += 1; agg[(kind, tn)][1] += nb
for (kind, tn), (c, nb) in sorted(agg.items()):
    print(f"{kind:7s} {tn:8s} {c:5d} tensors {nb/1e9:8.2f} GB")
