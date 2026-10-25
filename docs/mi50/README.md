# DeepSeek-V4.1-Flash-1017 on 2x AMD MI50 16 GB (gfx906)

This branch (`gfx906-deepseek`, on Project Maya v1.1.27) runs Maya's DeepSeek engine, `maya-ds4`, on gfx906 cards.
It adds three changes to Maya and the scripts, configs and measurements from my box. Write-up:
[blog.sbm-labs.com/en/posts/mi50-deepseek-v41](https://blog.sbm-labs.com/en/posts/mi50-deepseek-v41/).

| Commit | What |
|---|---|
| HIP: gfx906 as a wave64 target | the same edits as upstream PR #397 (gfx906 in the wave64 lists, `__dp4a` -> `v_dot4_i32_i8`) |
| ds4: Engram rows without readahead | `posix_fadvise(POSIX_FADV_RANDOM)` on the Engram reader (Linux); `DS4_EG_RANDOM=0` restores the old reads |
| pack_gguf: `--engram-meta`, `--partial-split` | pack ISTA-DASLab's GSQ-RCO GGUFs (their shards lack the Engram hash parameters and the DSpark geometry); use Maya-XS's model shards with another Engram set |

The scripts are the ones I ran: they use my paths (`/root/strata-ab/...`) and the
`strata-gfx906:0.1.47-011c9e6` image (mixa3607's ROCm 7.14 gfx906 base with cmake/ninja). Adjust both.

## The box

2x MI50 / Radeon Pro VII 16 GB (gfx906), PCIe 3.0 x16, no P2P, **75 W cap per card**, passive cooling; 12 cores of a
Xeon E5-2680 v4 (AVX2), 62.5 GiB RAM, NVMe; Proxmox LXC, everything in Docker. Every GPU job ran under a temperature
watchdog that kills it at 80 C.

## Build

```sh
scripts/build-maya-906.sh 1 maya-ds4      # cmake: STRATA_ENABLE_HIP=ON, CMAKE_HIP_ARCHITECTURES=gfx906, STRATA_PREFILL_MMQ=ON,
                                          # STRATA_NATIVE_EXPERTS=ON, STRATA_GGML_DIR=llama.cpp 3cf03257, no hipBLASLt
```

Kernel check (no model needed): `ds4_gguf_test` passes on gfx906 except the IQ4_XS/Q4_K window path, which matches the
reference but is not bit-identical to the token path; `hip_intrinsics` passes.

## Models and packs

- [ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF](https://huggingface.co/ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF)
  rev `cb02422c`: IQ1_M (121 GB, the default here), IQ2_XXS (138 GB), and `DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf` (111 GB)
- unsloth's `DeepSeek-V4.1-Flash-1017-UD-Q8_K_XL-00001-of-00009.gguf` (5.8 MB, metadata only) for `--engram-meta`
- a DSpark drafter: Maya-XS's `dspark/dspark-xs2.{bin,json}` (4.25 GB) from
  [peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF](https://huggingface.co/peasantsmith/DeepSeek-V4.1-Flash-1017-Maya-GGUF)

```sh
# the Engram set folder holds only the Engram GGUF (Maya reads every GGUF in it)
python3 tools/ds4/pack_gguf.py --model IQ1_M --out IQ1_M/maya-ds4 --engram engram/ \
  --engram-meta DeepSeek-V4.1-Flash-1017-UD-Q8_K_XL-00001-of-00009.gguf --drafter dspark/dspark-xs2.json
# Maya-XS shards 1-3 + ISTA's Engram instead of its own 161 GB of Q6_K tables
python3 tools/ds4/pack_gguf.py --model Maya-XS --partial-split --engram engram/ --engram-meta <UD shard 1> \
  --drafter dspark/dspark-xs2.json
```

## Run

`configs/maya-ds4-ista-iq1m-prod.json` (the server: `python3 serve/server.py --engine strata --config ...`):
`--tp 2` (falls back to a layer split: GPU 0 layers 0-19, GPU 1 layers 20-39 + head), `--max-context 262144`,
`--reserve-mib 1024`, `--dspark none`, `--vision off`, env `MAYA_DS4_SLOT_KEEP=1`. Maya picks 10 CPU-lane threads on the
12 cores (12 was slower), keeps ~2,570 experts in VRAM and computes the other ~12,800 (95 GB) on the CPU, reading them
in place through the page cache. `scripts/serve-maya.sh` and `scripts/deepseek-maya.service` are how I run it.

## Results (75 W per card, ROCm 7.14)

Decode medians in tokens/s over 3 answers of 128 tokens after a 256-token warm-up, page cache evicted before each arm
(`bench/ds_cmp_queue.sh`); prompt read in tokens/s.

| Engine, model | 4k prose | code gen | code edit | prompt read 4k / 271 / 1,384 | PPL (3k tokens) |
|---|---:|---:|---:|---|---:|
| Maya, ISTA IQ1_M (this branch) | 11.10 | 7.77 | 8.23 | 68.9 / 17.1 / 46.2 | 5.61 |
| Maya, ISTA IQ1_M (before the Engram change) | 9.96 | 9.97 | 9.24 | 71.9 / 14.9 / 46.2 | |
| Maya, Maya-XS | 8.44 | 9.53 | 9.48 | 58.4 / 17.4 / 4.5 | 5.47 |
| Maya, ISTA IQ2_XXS (this branch) | 9.36 | 6.26 | 7.15 | 48.8 / 14.0 / 2.7 | 5.35 |
| Strata 0.2.4.2 dsv41, ISTA IQ1_M, `--cpu-threads 10` | 8.48 | 9.18 | 10.13 | 40.4 / 8.8 / 9.4 | |

- Per token (`DS4_PROF=1`, warm): attention 28.1 ms + router/shared expert 11.3 + experts on the GPU 9.6, then
  **40.5 ms waiting for the CPU lane** (cold page cache: 233 ms). `results/M4-ds4-prof.txt`.
- DSpark (dspark-xs2): 79-92% of first drafts kept, ~2.2 tokens a pass, decode not faster (8.81 vs 10.10 in the same
  repeated-prompt test): verify windows multiply the CPU lane's work and the drafter's 4.25 GB cost ~600 VRAM experts.
- opencode agent tasks (`results/agent-*.jsonl`), all pass: t1 362 -> 205 s and t4 407 -> 324 s with the Engram change,
  t2 398 s, t3 365 s, t5 (long context) 591 s. The change removed the 50 s decode freezes; 10-20 s stalls remain on the
  long-context task.
- Perplexity: BOS + 1.5k tokens of my own Python + 1.5k of my own English prose (`bench/make_ppl_ids.py`), one sequence:
  a relative check between quants, not a benchmark.

## Strata 0.2.4.2's DeepSeek engine on gfx906

`strata/strata-dsv41-wave64-port.py` moves Maya's wave64 layer into Strata (62 lines, 4 files, all under
`STRATA_HIP_WAVE64`); build with the plain HIP backend (`STRATA_ENABLE_HIP=ON`, `CMAKE_HIP_ARCHITECTURES=gfx906`) -
Strata's CMake keeps `strata-dsv41` out of `STRATA_HIP_GFX906` builds. **Pass `--cpu-threads 10`**: it sizes its CPU
lane from the host's cores, not the container's cpuset, and ran 28 threads on 12 cores (1.8 tok/s).

## Caveats

- One card reached 79 C (junction) in a 10-minute agent task at 75 W: long sessions on passive cards sit near the
  80 C watchdog.
- The host went down once at the start of a cold IQ2_XXS prompt read (41-54 C, so not heat); not reproduced.
- Not tested: NVIDIA with the Engram change, mixed wave32/wave64 builds, more than two gfx906 cards.

The engine work is Project Maya's (MIT, see LICENSE); the gfx906 wave64 registration follows upstream PR #397.
This branch was made with Claude Code as an agent under my direction; every number above is from a logged run in
`results/`.
