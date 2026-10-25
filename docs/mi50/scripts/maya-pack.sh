#!/bin/bash
# Maya's pack (tools/ds4/pack_gguf.py: index, Engram hash tables, tokenizer - no weights copied) for a DeepSeek-V4.1 GGUF
# set under /root/strata-ab/models, in the gfx906 image (CPU only).  maya-pack.sh <model dir under models/> [pack_gguf args...]
# e.g. maya-pack.sh ds41-ista/IQ1_M --engram /models/ds41-ista/engram
set -u
D=$1; shift
docker run --rm --name maya-pack -v /root/strata-ab/src/maya-port:/maya:ro -v /root/strata-ab/models:/models -w /maya \
  strata-gfx906:0.1.47-011c9e6 python3 tools/ds4/pack_gguf.py --model /models/$D --out /models/$D/maya-ds4 "$@" \
  2>&1 | tee /root/strata-ab/logs/maya-pack-$(echo $D | tr / _).log
