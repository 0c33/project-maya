#!/bin/bash
# Strata 0.2.4.2's DeepSeek engine (strata-dsv41, Strata's port of Project Maya's maya-ds4) on the two MI50s: the
# strata-ab wave64 transplant (build/strata-dsv41-wave64-port.py) on src/Strata-0242, built with the plain HIP backend.
# Server: Strata's serve/server.py.  Always under the watchdog:  safe-run.sh -l 80 -- serve-strata-dsv41.sh
# Knobs: CFG (configs/, default strata-dsv41-ista-iq1m.json), PUBLISH (127.0.0.1:8181), EXTRA_DOCKER, IMAGE.
IMAGE=${IMAGE:-strata-gfx906:0.1.47-011c9e6}
CFG=${CFG:-strata-dsv41-ista-iq1m.json}
exec docker run --rm --name strata-dsv41 --label gfxjob=1 --ulimit core=0 \
  --device=/dev/kfd --device=/dev/dri --group-add 992 --group-add 44 --ipc=host --shm-size 2g \
  -p "${PUBLISH:-127.0.0.1:8181}":8181 \
  -v /root/strata-ab/src/Strata-0242:/s -v /root/strata-ab/models:/models \
  -v /root/strata-ab/configs:/cfg:ro -v /root/strata-ab/logs:/logs -w /s \
  ${EXTRA_DOCKER:-} "$IMAGE" \
  python3 serve/server.py --engine strata --config /cfg/"$CFG" --host 0.0.0.0 --port 8181
