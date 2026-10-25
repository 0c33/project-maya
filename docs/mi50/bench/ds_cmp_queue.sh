#!/bin/bash
# Head-to-head arms on equal terms: page cache evicted (bench/evict.py) and Strata's conversation slots cleared before
# each, then WARMUP=256 REPS=3 on the 4k prose prompt and the two code prompts.  ds_cmp_queue.sh "<eng> <tag> <cfg>" ...
cd /root/strata-ab
for arm in "$@"; do
  set -- $arm
  python3 -I bench/evict.py models/ds41-ista models/ds41-maya models/ds41-1017 >/dev/null
  rm -rf logs/ds4-slots
  echo "=== $2 ($1, $3) $(date +%T)"
  WARMUP=256 REPS=3 timeout 3600 bench/mds_dec_arm.sh $1 $2 $3 4096 codegen codeedit 2>&1 | grep -E 'ready after|rep[0-9]|prime:|median|did not'
done
echo "queue done $(date +%T)"
