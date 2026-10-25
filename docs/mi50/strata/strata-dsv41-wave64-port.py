#!/usr/bin/env python3
"""Port Project Maya's wave64 (gfx908) HIP compat layer into Strata 0.2.4.x so strata-dsv41 (Strata's port of maya-ds4)
builds and runs on gfx906 (MI50 / Radeon Pro VII) through the plain HIP backend (STRATA_ENABLE_HIP, not STRATA_HIP_GFX906).

Usage: strata-dsv41-wave64-port.py <Strata checkout>   (idempotent: a file already ported is left alone)

What it changes (all of it gated on STRATA_HIP_WAVE64, which only gfx906 / gfx908 builds define):
  cmake/hip_backend.cmake                 gfx906 / gfx908 accepted as wave64; STRATA_HIP_WAVE64=1 on strata_hip_runtime
  include/strata/hip_compat/cuda_runtime.h HIP's own warp-sync builtins off (they span all 64 lanes); mapped host memory
                                           allocated coherent (GPU/CPU doorbells spin on it)
  include/strata/hip_compat/intrinsics.hpp signed dot4 on gfx906 / gfx908; __syncwarp with wavefront fences; ballot of the
                                           caller's 32-lane half; __nanosleep scaled
  src/core/device.cu                      wave64 accepted when the build is a wave64 one
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])


def edit(rel, pairs):
    p = root / rel
    s = p.read_text()
    if "STRATA_HIP_WAVE64" in s or "_strata_hip_wave64" in s:
        print("already ported:", rel)
        return
    for old, new in pairs:
        if old not in s:
            raise SystemExit("%s: anchor not found:\n%s" % (rel, old))
        s = s.replace(old, new, 1)
    p.write_text(s)
    print("ported:", rel)


edit("cmake/hip_backend.cmake", [
    ("foreach(_arch IN LISTS _strata_hip_norm)",
     "# gfx906 (MI50 / Radeon Pro VII, Vega 20) and gfx908 (MI100) are wave64: they run the CUDA-shaped kernels through\n"
     "# Project Maya's logical-32-lane half-wavefront mapping (hip_compat/intrinsics.hpp, STRATA_HIP_WAVE64). strata-ab port.\n"
     "set(_strata_hip_wave64 gfx906 gfx908)\n"
     "foreach(_arch IN LISTS _strata_hip_norm)"),
    ("  elseif(_base IN_LIST _strata_hip_unvalidated)",
     "  elseif(_base IN_LIST _strata_hip_wave64)\n"
     "    message(STATUS \"Strata HIP: ${_base} is a wave64 card running through the half-wavefront compat layer (experimental)\")\n"
     "  elseif(_base IN_LIST _strata_hip_unvalidated)"),
    ("target_compile_definitions(strata_hip_runtime INTERFACE STRATA_USE_HIP=1 \"STRATA_HIP_ARCHS=\\\"${STRATA_HIP_ARCHS}\\\"\")",
     "set(STRATA_HIP_WAVE64 OFF)\n"
     "foreach(_a IN LISTS STRATA_HIP_ARCH_LIST)\n"
     "  if(_a IN_LIST _strata_hip_wave64)\n"
     "    set(STRATA_HIP_WAVE64 ON)\n"
     "  endif()\n"
     "endforeach()\n"
     "target_compile_definitions(strata_hip_runtime INTERFACE STRATA_USE_HIP=1 \"STRATA_HIP_ARCHS=\\\"${STRATA_HIP_ARCHS}\\\"\"\n"
     "  $<$<BOOL:${STRATA_HIP_WAVE64}>:STRATA_HIP_WAVE64=1>)"),
])

edit("include/strata/hip_compat/cuda_runtime.h", [
    ("#include <hip/hip_runtime.h>",
     "#ifdef STRATA_HIP_WAVE64\n"
     "// wave64 (gfx906 / gfx908): HIP's own warp-sync builtins would span the whole 64-lane wavefront and break every\n"
     "// kernel's reduction order; intrinsics.hpp supplies the logical-32-lane-half mapping instead (Project Maya's layer).\n"
     "#ifndef HIP_DISABLE_WARP_SYNC_BUILTINS\n"
     "#define HIP_DISABLE_WARP_SYNC_BUILTINS 1\n"
     "#endif\n"
     "#endif  // STRATA_HIP_WAVE64\n"
     "#include <hip/hip_runtime.h>"),
    ("#define cudaHostAlloc hipHostMalloc\n",
     "#ifdef STRATA_HIP_WAVE64\n"
     "// Mapped host memory is where a running kernel and the CPU spin on each other's words: on these cards it must be\n"
     "// fine-grained (coherent), or the spin may never see the other side (Project Maya's wave64 rule).\n"
     "inline hipError_t cudaHostAlloc(void** p, size_t bytes, unsigned int flags) {\n"
     "    if (flags & hipHostMallocMapped) flags |= hipHostMallocCoherent;\n"
     "    return hipHostMalloc(p, bytes, flags);\n"
     "}\n"
     "template <typename T>\n"
     "inline hipError_t cudaHostAlloc(T** p, size_t bytes, unsigned int flags) {\n"
     "    return cudaHostAlloc(reinterpret_cast<void**>(p), bytes, flags);\n"
     "}\n"
     "#else\n"
     "#define cudaHostAlloc hipHostMalloc\n"
     "#endif  // STRATA_HIP_WAVE64\n"),
])

edit("include/strata/hip_compat/intrinsics.hpp", [
    ("#elif defined(__gfx1012__) && !defined(STRATA_GFX1012_PORTABLE_DOT)",
     "#elif (defined(__gfx906__) || defined(__gfx908__)) && __has_builtin(__builtin_amdgcn_sdot4)\n"
     "    // Vega 20 (MI50) / CDNA1 (MI100): v_dot4_i32_i8 (dot1-insts), the signed dot4 of the wave64 compat layer.\n"
     "    return __builtin_amdgcn_sdot4(a, b, c, false);\n"
     "#elif defined(__gfx1012__) && !defined(STRATA_GFX1012_PORTABLE_DOT)"),
    ("// Older HIP has no __syncwarp.",
     "#ifdef STRATA_HIP_WAVE64\n"
     "// wave64: __syncwarp as wavefront-scope release/acquire fences around a wave barrier (HIP's own is disabled).\n"
     "__device__ __forceinline__ void syncwarp(uint32_t mask = 0xffffffffu) {\n"
     "    require_full_wave_mask(mask);\n"
     "    __builtin_amdgcn_fence(__ATOMIC_RELEASE, \"wavefront\");\n"
     "    __builtin_amdgcn_wave_barrier();\n"
     "    __builtin_amdgcn_fence(__ATOMIC_ACQUIRE, \"wavefront\");\n"
     "}\n"
     "#else\n"
     "// Older HIP has no __syncwarp."),
    ("    return static_cast<unsigned>(__ballot(predicate));",
     "#ifdef STRATA_HIP_WAVE64\n"
     "    // wave64: a CUDA warp is the caller's 32-lane half; lanes 32..63 see their own half's bits.\n"
     "    return static_cast<unsigned>(__ballot(predicate) >> (__lane_id() & 32));\n"
     "#else\n"
     "    return static_cast<unsigned>(__ballot(predicate));\n"
     "#endif"),
])

# the #endif that closes "#else // Older HIP..." and the macro block: placed after the old syncwarp definition
p = root / "include/strata/hip_compat/intrinsics.hpp"
s = p.read_text()
if "#endif  // STRATA_HIP_WAVE64 (syncwarp)" not in s:
    i = s.index("// Older HIP has no __syncwarp.")
    j = s.index("#endif", s.index("__device__ __forceinline__ void syncwarp", i))   # the HIP_VERSION_MAJOR < 7 block's end
    j = s.index("\n", j) + 1
    s = s[:j] + "#endif  // STRATA_HIP_WAVE64 (syncwarp)\n" + s[j:]
    old_sync = "#if HIP_VERSION_MAJOR < 7\n#define __syncwarp(...) (::strata::hip_compat::syncwarp(__VA_ARGS__))\n#endif"
    if old_sync in s:
        s = s.replace(old_sync,
                      "#ifdef STRATA_HIP_WAVE64\n#define __syncwarp(...) (::strata::hip_compat::syncwarp(__VA_ARGS__))\n"
                      "#elif HIP_VERSION_MAJOR < 7\n#define __syncwarp(...) (::strata::hip_compat::syncwarp(__VA_ARGS__))\n#endif", 1)
    else:
        raise SystemExit("intrinsics.hpp: __syncwarp macro block not found")
    old_sleep = "#define __nanosleep(cycles) __builtin_amdgcn_s_sleep(1)"
    if old_sleep in s:
        s = s.replace(old_sleep,
                      "#ifdef STRATA_HIP_WAVE64\n#define __nanosleep(ns) __builtin_amdgcn_s_sleep((ns) >= 400u ? 8u : 1u)\n#else\n"
                      + old_sleep + "\n#endif", 1)
    p.write_text(s)
    print("ported: intrinsics.hpp syncwarp/nanosleep macros")

edit("src/core/device.cu", [
    ("    if (p.warpSize != 32) {\n        return card + \" runs wave\" + std::to_string(p.warpSize) + \"; Strata's HIP kernels need wave32\";\n    }",
     "#ifdef STRATA_HIP_WAVE64\n"
     "    if (p.warpSize != 32 && p.warpSize != 64) {   // (wave64 gfx906 / gfx908: the compat layer's half-wavefront mapping)\n"
     "#else\n"
     "    if (p.warpSize != 32) {\n"
     "#endif\n"
     "        return card + \" runs wave\" + std::to_string(p.warpSize) + \"; Strata's HIP kernels need wave32\";\n    }"),
])
print("done")
