#!/bin/bash
# Project Maya (v1.1.27 + gfx906 port, src/maya-port: wave64 compat layer, sdot4) serving DeepSeek-V4.1-Flash-1017
# (maya-ds4) on the two MI50s.  Server: Maya's serve/server.py (OpenAI + Anthropic API, DSML tool calls).
# Always under the watchdog:  /root/gfx-build/gpu-tune/safe-run.sh -l 80 -- /root/strata-ab/serve-maya.sh
# Knobs: CFG (configs/, default maya-ds4-ista-iq1m.json), PUBLISH (127.0.0.1:8171), EXTRA_DOCKER, IMAGE.
IMAGE=${IMAGE:-strata-gfx906:0.1.47-011c9e6}
CFG=${CFG:-maya-ds4-ista-iq1m.json}
exec docker run --rm --name maya --label gfxjob=1 --ulimit core=0 \
  --device=/dev/kfd --device=/dev/dri --group-add 992 --group-add 44 --ipc=host --shm-size 2g \
  -p "${PUBLISH:-127.0.0.1:8171}":8171 \
  -v /root/strata-ab/src/maya-port:/maya -v /root/strata-ab/models:/models \
  -v /root/strata-ab/configs:/cfg:ro -v /root/strata-ab/logs:/logs -w /maya \
  ${EXTRA_DOCKER:-} "$IMAGE" \
  python3 serve/server.py --engine strata --config /cfg/"$CFG" --host 0.0.0.0 --port 8171
