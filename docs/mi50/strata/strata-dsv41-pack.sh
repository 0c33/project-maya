#!/bin/bash
# Strata's DeepSeek pack (tools/dsv41/pack_gguf.py, the "plain recipe" of docs/DEEPSEEK41.md for the IST-DAS sets) in the
# gfx906 image (CPU only).  strata-dsv41-pack.sh <set dir under models/ds41-ista/> <profile 2.00|2.25>
set -u
SET=$1 PROF=${2:-2.00}
S=/models/ds41-ista
docker run --rm --name strata-pack -v /root/strata-ab/src/Strata-0242:/s:ro -v /root/strata-ab/models:/models -w /s \
  strata-gfx906:0.1.47-011c9e6 bash -c "
python3 tools/dsv41/pack_gguf.py --model $S/$SET --out $S/$SET/strata-dsv41 \
  --engram $S/shared/DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf \
  --engram-meta $S/shared/DeepSeek-V4.1-Flash-1017-UD-Q8_K_XL-00001-of-00009.gguf \
  --dspark-gguf $S/shared/dspark-DeepSeek-V4.1-Flash-1017-Q8_0.gguf && \
cp data/dsv41/profile-$PROF.bin $S/$SET/strata-dsv41/expert-profile.bin && echo PACK_OK" 2>&1 | tee /root/strata-ab/logs/strata-pack-$SET.log
