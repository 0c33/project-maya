#!/bin/bash
# Maya / Strata-dsv41 DeepSeek-V4.1 arm, measured like ds_dec_arm.sh (Xolotl): a fresh server with a config variant,
# decode after the fixed 4k prompt (x3, 128 tokens) plus the two code prompts, the engine's own summary lines printed.
#   mds_dec_arm.sh <maya|strata> <tag> <config in configs/> [abbench lengths, default "4096 codegen codeedit"]
#   env: EXTRA_DOCKER ("-e K=V ..."), REPS (3), MAX_TOKENS (128), KEEP=1 (leave the server running afterwards)
set -u
ENG=$1 TAG=$2 CFG=$3; shift 3
LENS=${*:-4096 codegen codeedit}
L=/root/strata-ab/logs
case $ENG in
  maya)   NAME=maya;         PORT=8171; SERVE=/root/strata-ab/serve-maya.sh;         ELOG=$L/maya-ds4-engine.log ;;
  strata) NAME=strata-dsv41; PORT=8181; SERVE=/root/strata-ab/serve-strata-dsv41.sh; ELOG=$L/strata-dsv41-engine.log ;;
  *) echo "engine: maya or strata"; exit 2 ;;
esac
for c in ds41 maya strata-dsv41; do docker stop $c >/dev/null 2>&1; tmux kill-session -t $c 2>/dev/null; done
sleep 3
: > $ELOG
tmux new-session -d -s $NAME "CFG=$CFG EXTRA_DOCKER='${EXTRA_DOCKER:-}' /root/gfx-build/gpu-tune/safe-run.sh -l 80 -- $SERVE 2>&1 | tee $L/$NAME-serve-$TAG.log"
t0=$(date +%s)
until grep -qE '^ready:' $L/$NAME-serve-$TAG.log 2>/dev/null; do
  if grep -qE 'END rc=|Traceback|engine (exited|died|stopped)' $L/$NAME-serve-$TAG.log 2>/dev/null || [ $(( $(date +%s) - t0 )) -gt 1800 ]; then
    echo "[$TAG] server did not come up"; tail -25 $L/$NAME-serve-$TAG.log; tail -40 $ELOG; exit 1; fi
  sleep 5
done
echo "[$TAG] ready after $(( $(date +%s) - t0 )) s ($ENG, $CFG, ${EXTRA_DOCKER:-})"
cd /root/strata-ab/bench
COOL_C=50 ABORT_C=76 REPS=${REPS:-3} MAX_TOKENS=${MAX_TOKENS:-128} /root/gfx-build/gpu-tune/safe-run.sh -l 80 -- \
  python3 abbench.py http://127.0.0.1:$PORT deepseek-v4.1-flash-1017 $TAG decode $LENS
cp $ELOG $ELOG.$TAG
python3 summarize.py /root/strata-ab/results $TAG | grep -E "==|decode|prime"
if [ "${KEEP:-0}" != 1 ]; then docker stop $NAME >/dev/null 2>&1; tmux kill-session -t $NAME 2>/dev/null; fi
