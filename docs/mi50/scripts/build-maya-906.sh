#!/bin/bash
# Maya (mw00/project-maya, gfx906 port in /root/strata-ab/src/maya-port) built for gfx906 in the ROCm 7.14 gfx906 image.
# Usage: build-maya-906.sh <log-tag> [targets...]   (default target maya-ds4)
TAG=${1:-1}; shift
T=${*:-maya-ds4}
LOG=/root/strata-ab/logs/maya-build-$TAG.log
docker run --rm --name maya-build -v /root/strata-ab/src/maya-port:/maya -v /root/strata-ab/src/llama-3cf03257/llama.cpp:/llama:ro \
  -w /maya strata-gfx906:0.1.47-011c9e6 bash -c "
set -e
export PATH=/opt/rocm/bin:/opt/rocm/llvm/bin:\$PATH ROCM_PATH=/opt/rocm HIP_PATH=/opt/rocm HIP_PLATFORM=amd
if [ ! -f build-906/build.ninja ]; then
  cmake -S . -B build-906 -G Ninja -DCMAKE_BUILD_TYPE=Release -DSTRATA_ENABLE_HIP=ON -DSTRATA_ENABLE_CUDA=OFF \
    -DSTRATA_PREFILL_MMQ=ON -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_BUILD_TESTS=OFF -DCMAKE_HIP_ARCHITECTURES=gfx906 \
    -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ -DCMAKE_PREFIX_PATH=/opt/rocm -DSTRATA_GGML_DIR=/llama \
    -DCMAKE_DISABLE_FIND_PACKAGE_hipblaslt=ON -DCMAKE_MAKE_PROGRAM=/venv/bin/ninja
fi
cmake --build build-906 --target $T -j \${JOBS:-8}
ls -la build-906/maya-ds4 build-906/bin/maya-ds4 2>/dev/null || true
" > $LOG 2>&1
echo "exit=$?" >> $LOG
