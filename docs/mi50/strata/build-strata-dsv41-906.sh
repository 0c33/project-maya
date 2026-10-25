#!/bin/bash
# strata-dsv41 (Strata 0.2.4.2 + strata-dsv41-wave64-port.py) for gfx906 through the plain HIP backend, in the ROCm 7.14 gfx906 image.
TAG=${1:-1}; shift; T=${*:-strata-dsv41}
LOG=/root/strata-ab/logs/strata-dsv41-build-$TAG.log
docker run --rm --name strata-dsv41-build -v /root/strata-ab/src/Strata-0242:/s -v /root/strata-ab/src/llama-3cf03257/llama.cpp:/llama:ro \
  -w /s strata-gfx906:0.1.47-011c9e6 bash -c "
set -e
export PATH=/opt/rocm/bin:/opt/rocm/llvm/bin:\$PATH ROCM_PATH=/opt/rocm HIP_PATH=/opt/rocm HIP_PLATFORM=amd
if [ ! -f build-dsv41-906/build.ninja ]; then
  cmake -S . -B build-dsv41-906 -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_MAKE_PROGRAM=/venv/bin/ninja \
    -DSTRATA_ENABLE_HIP=ON -DCMAKE_HIP_ARCHITECTURES=gfx906 -DSTRATA_BUILD_TESTS=OFF -DSTRATA_BUILD_DSV41=ON \
    -DSTRATA_NATIVE_EXPERTS=ON -DSTRATA_GGML_DIR=/llama -DCMAKE_HIP_COMPILER=/opt/rocm/llvm/bin/clang++ \
    -DCMAKE_HIP_COMPILER_ROCM_ROOT=/opt/rocm '-DCMAKE_HIP_FLAGS=--rocm-path=/opt/rocm --rocm-device-lib-path=/opt/rocm/amdgcn/bitcode' \
    -DCMAKE_PREFIX_PATH=/opt/rocm -DCMAKE_DISABLE_FIND_PACKAGE_hipblaslt=ON
fi
cmake --build build-dsv41-906 -j \${JOBS:-6} --target $T -- -k 0
ls -la build-dsv41-906/strata-dsv41 build-dsv41-906/bin/strata-dsv41 2>/dev/null || true
" > $LOG 2>&1
echo "exit=$?" >> $LOG
