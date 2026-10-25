#!/bin/bash
# Perplexity of the fixed 3k-token text (data/ppl/ppl3k.ids, the same ids as ds41_ppl.sh) on maya-ds4 (gfx906 port),
# one forward of the whole sequence, both GPUs.  maya_ppl.sh <tag> <pack dir under /models> [extra engine args...]
# env: ENGINE (default /maya/build-906/maya-ds4), SRC (default src/maya-port), E (extra docker -e args)
set -u
TAG=$1 PACK=$2; shift 2
SRC=${SRC:-/root/strata-ab/src/maya-port}
L=/root/strata-ab/logs/maya-ppl-$TAG.log
/root/gfx-build/gpu-tune/safe-run.sh -l 80 -- docker run --rm --name mayappl --label gfxjob=1 --ulimit core=0 \
  --device=/dev/kfd --device=/dev/dri --group-add 992 --group-add 44 --ipc=host --shm-size 2g -e HIP_VISIBLE_DEVICES=0,1 ${E:-} \
  -v "$SRC":/maya -v /root/strata-ab/models:/models -v /root/strata-ab/data/ppl:/ppl:ro -w /maya strata-gfx906:0.1.47-011c9e6 \
  ${ENGINE:-/maya/build-906/maya-ds4} --pack "$PACK" --max-context 8192 --tp 2 --reserve-mib 1024 --dspark none --vision off \
  "$@" --ppl /ppl/ppl3k.ids > "$L" 2>&1
echo "rc=$?" >> "$L"
grep -E '^perplexity|^ppl:|rc=' "$L"
