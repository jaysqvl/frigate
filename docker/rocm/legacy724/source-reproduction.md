# Owning the legacy runtime build

This work reproduces the documented 7.2.4 compatibility recipe from pinned
inputs. It does not assert that the new binaries are byte-identical to Gary's
release archive. Source compilation and offline qualification passed on
2026-10-21 UTC (October 20 locally). The candidate combines upstream Frigate
`0.19.0-5bb2cde` with the rebuilt runtime. It has not been deployed or run on the
GPU. Production and development retained their existing containers, images,
configuration, mounts and start times, and both remained healthy. The 10.1
experiments are archived with their evidence retained.

## Offline result

The candidate image is `frigate-local:owned724-source-20261021`, config image ID
`sha256:cf33fe1444469b48b3d25c1802c147f698cf51c99cf36e519148222567534fff`.
The machine-readable receipt is [source-assessment.json](source-assessment.json).

| Check | Result |
| --- | --- |
| Native dependency closure | All 30 packaged native libraries/helpers link; 29 standalone native symbol-relocation checks pass with zero missing libraries or undefined symbols |
| Python/application imports | Rebuilt CPython 3.11 binding and full Frigate application import together; CPU ORT 1.30.0 and `pip check` pass |
| CPU compiler checks | Raw HIPRTC and MIGraphX's installed HIPRTC helper both produce gfx900 code objects without GPU devices or enumeration |
| CPU execution | Reference and oneDNN CPU arithmetic pass |
| Actual YOLO model | Unchanged YOLO26s distilled model parses with input `(1, 3, 320, 320)` and output `(1, 300, 6)`; full inference is not run |
| Copied configuration | Actual saved config migrates from 0.18-0 to 0.19-0, preserves all five camera workloads, model/tuning, and recording-off state; second load is unchanged |
| Copied database | Migrations 036 through 039 pass; all old rows/columns and login records are preserved; integrity, foreign keys, exact backup and second-run idempotence pass |
| Permissions/isolation | UID 1000 can migrate copied config/DB and write the copied cache; no network, devices, host appdata, camera workers or media are exposed |
| Regression checks | 24 upstream config tests and 10 adapter tests pass in the Linux candidate; four input-lock tests and source lint/syntax checks pass separately |

The original private backup was hashed before and after and stayed unchanged.
Migrated evidence is saved privately. A portable runtime archive is preserved
outside Docker and checksum-verified. Build inputs, compiler objects and recipes
remain available for repeat builds; temporary qualification containers and
superseded outputs are cleaned up after acceptance.

These results qualify packaging and migration only. Fresh YOLO GPU compilation,
inference correctness, performance, and shared-GPU stability are still untested
for these new binaries. The running dev deployment continues using the earlier
qualified frozen binary runtime.

## What Gary actually builds

Gary's Frigate fork consumes a separately built MIGraphX archive, installs AMD's
ROCm packages, adds the old gfx900 rocBLAS kernel files, and builds a Python
binding for Frigate. The separate
[MIGraphX recipe](https://github.com/garymathews/AMDMIGraphX/blob/b7057cc3a8460f7bcea15ec20f2c1b4940a4b5ef/Dockerfile)
builds MIGraphX and prerequisites including classic rocMLIR and oneDNN. It does
not rebuild every ROCm component from source. Our recipe follows that division:
we own the build instructions and source pins while retaining official AMD
packages for HIP, MIOpen and rocBLAS.

The checked Gary recipe is commit
`b7057cc3a8460f7bcea15ec20f2c1b4940a4b5ef`. Its MIGraphX `src/` Git tree is
`56a22f66ece4c729743ac590ce82fdcd8d506dab`, identical to AMD commit
`07ef4ba4f9ef95d241b7be165e60ad148f3344ee` (`rocm-7.2.3`, MIGraphX 2.15.0).
The source lock uses that AMD commit. It is not a new AMD repository or a
rewritten inference engine.

Gary's `v7.2.4` tag points to commit
`6e8f5f6e1250a387454087e98519cc5c28350be8`, whose ORT pin says 1.26. The consumed
archive is named `migraphx-v7.2.4-1.29.0.tar.gz`; its hash is
`633279fbd5a1f7f16b9e60cfca312418890d66befbbcec60fe1067f739719882`.
The available release metadata does not prove the exact source and complete
build environment that produced that archive. The matching inference source
tree and documented recipe support a source reproduction, not historical binary
provenance. Our own builds record that provenance from this point onward.

## Complete compatibility checklist

| Layer | Gary's documented 7.2.4 method | Owned 7.2.4 recipe | Previously tested native 10.1 |
| --- | --- | --- | --- |
| GPU identity | Treat the APU as gfx900, `HSA_OVERRIDE_GFX_VERSION=9.0.0` | Retain | Native gfx90c instead |
| Math kernels | Add only gfx900 rocBLAS files from 6.3.4; retain the full 7.2.4 library directory and fallbacks | Retain, with the old Debian archive hash locked | SDK-provided gfx90c kernels; no equivalent source rocBLAS rebuild |
| MIGraphX | Build 2.15.0 with gfx900 included | Same inference source tree, pinned archive | Build 2.18.0 from a different pinned source |
| GPU target list | gfx900, gfx908, gfx90a, gfx942, gfx950, gfx1030, gfx1100, gfx1101, gfx1200, gfx1201 | Retain the full list | gfx90c only |
| MLIR backend | Classic rocMLIR commit `6671a1ee31d44e1f2f7743a26a71ffc4ce9169bf`, dialect API 4, fat rockCompiler library | Retain | Initially disabled, then classic rocMLIR with dialect API 6; separate stock-provider experiment used a different MLIR backend |
| CPU backend | Enabled, separately build and package oneDNN 1.8.1 with OpenMP and `-march=znver2`; prerequisite recipe also lists 1.7 | Build and link one pinned 1.8.1 tree; no duplicate 1.7 prerequisite | Disabled |
| Composable Kernel | Enabled, pinned dependency `b7775add2d28251674d81e220cd4a857b90b997a` | Retain | Disabled for legacy target |
| hipBLASLt | Enabled by the documented MIGraphX build defaults | Explicitly retain | Disabled for legacy target |
| Compiler | AMD ROCm Clang on Ubuntu 22.04 | Pin the AMD 7.2.4 SDK image and added packages | Different 10.1 SDK compiler and libraries |
| Build metadata workarounds | Remove an obsolete absolute `librt.so` path from MIOpen's CMake metadata; guard hipBLASLt `block()` syntax for older CMake | Retain the link-path correction; pinned CMake 3.31.10 understands `block()` directly | Different SDK package metadata |
| SDMA | Working deployment requires `HSA_ENABLE_SDMA=0` | Retain | Present in the direct-detector benchmarks; omitted in the failed stock-provider probe, corrected offline but not retested on GPU |
| Pass workarounds | Disable MIOpen fusion, scheduling pass and reduce fusion | Retain all three | Retained in the direct-detector build |
| HIPRTC workaround | `MIGRAPHX_ENABLE_HIPRTC_WORKAROUNDS=1` | Retain | The native 2.18 source does not reference this variable; setting it cannot be assumed to recreate the old implementation |
| Runtime compiler headers | C++ standard library headers plus their complete C/platform headers and GCC support files | Pinned GCC 14 and C/Linux development packages | Different SDK/header packaging |
| Runtime executables | Copy ROCm binaries, including the installed MIGraphX HIPRTC helper and driver | Retain native helpers in the MIGraphX layout with top-level aliases; qualify helper compilation on the CPU without GPU devices | Built from a different source/SDK |
| Cache directories | MIOpen user/find caches and AMD COMGR cache under the private model-cache directory | Retain | Retained in direct-detector tests |
| Detector | Direct MIGraphX Python binding and Gary's model/output handling | Existing restored adapter retained | Same direct detector, plus rocBLAS initialization before loading the native cached program |
| Compile options | Fast math and conserve CPU default true; exhaustive tuning configurable | Preserve this installation's true/true/true profile and `offload_copy=True` | True/true/true; matching native MLIR cache was compiled with `offload_copy=True`, but MLIR tuning was capped at eight candidates |
| Python ABI | Separate binding compiled for Frigate's Python version | Rebuild CPython 3.11 binding from the same source | Different native 10.1 binding |
| ONNX Runtime | Custom MIGraphX-enabled ORT 1.29 wheel alongside the direct detector | Keep upstream CPU ORT 1.30.0 alongside the direct MIGraphX binding | Direct-detector benchmarks and the later standard ORT-provider experiment are separate implementations |
| Video decode | Backported Mesa VA/Vulkan packages in Gary's image | Keep the official Frigate application's decode stack; this is a packaging difference | Not a controlled ROCm inference optimization |

The three disabled passes are `MIGRAPHX_DISABLE_MIOPEN_FUSION=1`,
`MIGRAPHX_DISABLE_SCHEDULE_PASS=1`, and `MIGRAPHX_DISABLE_REDUCE_FUSION=1`.
Cache settings and the complete environment are explicit in both Dockerfiles.
The independently downloaded NUMA library, OpenMP library and `features.h`
match the accepted frozen runtime's saved SHA256 values exactly. The original
Debian archives are extracted on Linux, preserving its case-sensitive header
names.
These build differences do not establish which component caused a performance
difference. In particular, an enabled backend need not be selected for this GPU
or model, and a disabled CPU backend does not by itself explain GPU latency.

The offline recipe also preserves the required MIOpen/rocBLAS fallback paths and
development headers. It deliberately packages the inference dependency closure,
instead of Gary's unused Python 3.10 binding and optional HIP FFT/sparse/random
tools. Those optional components were not fully linked in the accepted frozen
runtime either. This is a Frigate direct-detector runtime, not certification of
the entire ROCm SDK or other Frigate AI features.

Gary's builder also installs PyTorch, Torchvision, Triton, test tools and an ORT
source checkout. Those are not dependencies of the enabled MIGraphX C++ runtime
and separate Frigate Python binding. They are omitted here along with GPU tests.
The source recipe replaces floating `rbuild`/recipe downloads with explicit
pinned prerequisites. Its separately pinned pybind11 input may differ from the
floating Debian pybind11 package used by Gary's Frigate binding stage. These are
documented build and packaging differences, not an assertion of literal command
or historical binary equivalence.

The published builder runs `rbuild prepare -s develop`, whose `rbuild.ini` also
lists oneDNN 1.7. It then separately builds oneDNN 1.8.1 and copies that tree into
the packaged output. The recipe does not explicitly select the separate 1.8.1
tree during MIGraphX configuration. Our single 1.8.1 build removes that ambiguity,
but cannot establish which CPU headers Gary's historical archive used.

Build-only switches are preserved where applicable: `BUILD_TESTING=OFF`,
`LLVM_INCLUDE_TESTS=OFF`, `CK_BUILD_JIT_LIB=ON`, position-independent code,
oneDNN's OpenMP runtime and `-march=znver2`, and disabled oneDNN/msgpack examples
and tests. Gary writes `/opt/rocm/lib` and `/opt/rocm/lib/migraphx/lib` to the
loader configuration, plus `/usr/lib/llvm-14/lib`. Our recipe keeps the first two
paths and installs the exact working OpenMP binary in the standard system
library directory. Gary's accepted image contains that binary under LLVM 19,
so reproducing its LLVM 14 loader entry would not resolve it. Gary's HSA override
is a configurable build argument; this recipe deliberately pins it to `9.0.0`
for this installation's APU profile.

## What other legacy builders establish

[Schaka's builder at commit 18d9712baa5621e394c2d066fca8ee93cf02e42c](https://github.com/Schaka/rocm-migraphx-ort-builder/tree/18d9712baa5621e394c2d066fca8ee93cf02e42c)
lists gfx900, gfx906 and gfx90c as legacy GCN targets. Its
[MIGraphX script](https://github.com/Schaka/rocm-migraphx-ort-builder/blob/18d9712baa5621e394c2d066fca8ee93cf02e42c/scripts/build/migraphx.sh)
disables CK and hipBLASLt for those targets. Its
[legacy patch](https://github.com/Schaka/rocm-migraphx-ort-builder/blob/18d9712baa5621e394c2d066fca8ee93cf02e42c/scripts/build/migraphx-patch-legacy.sh)
removes the CK dependency and fixes the unguarded `gfx_default_rocblas()` call.
Our native 10.1 patch handles that same call-site problem. Enabling CK or
hipBLASLt is therefore not an established missed legacy optimization.

However, its
[rocBLAS build](https://github.com/Schaka/rocm-migraphx-ort-builder/blob/18d9712baa5621e394c2d066fca8ee93cf02e42c/scripts/build/rocblas.sh)
rebuilds architecture-specific Tensile kernels from source for release builds,
using `rmake.py -i -a <arch> --no_hipblaslt`. Our 10.1 tests relied on SDK kernels.
That method remains untested in this project.

The builder reports MIGraphX/ORT model dispatch on gfx1010 hardware. It does not
document a gfx90c MIGraphX inference result. Listed build targets, provider
imports, Torch extension checks, and successful artifact construction do not
prove the 5700G can safely run our Frigate model.

Our isolated direct-detector tests found about 12% and 17% slower latency for
the tested native 10.1 builds in separate sessions. They compare those complete
builds with 7.2.4, not just the ROCm version or MLIR flag. The native MLIR cold
compile receipt has the same cache hash as its timed benchmark passes. It proves
fast math was enabled, but `MIGRAPHX_MLIR_TUNE_LIMIT=8` bounded the search despite
`exhaustive_tune=True`. That run did not match unrestricted tuning. The earlier
7.2.4 compile log also records fast math and exhaustive tuning, but lacks a cache
checksum connecting it conclusively to the later timed cache. These are limits
on compile provenance and comparability, not a reason to discard the measured
latencies. No faithful Gary-style 10.1 port or source-rebuilt 10.1 rocBLAS
experiment has been qualified. The stock provider experiment never passed
functional qualification and has no valid performance result.

## Repeating the owned build

`source-lock.json` pins source archives, compiler image, application image,
kernel package and builder packages. `runtime-os-lock.json` separately pins the
runtime OS support files. Downloading is a separate step from compilation:

```sh
python3 docker/rocm/legacy724/source_inputs.py fetch \
  --lock docker/rocm/legacy724/source-lock.json --root inputs
python3 docker/rocm/legacy724/source_inputs.py fetch \
  --lock docker/rocm/legacy724/runtime-os-lock.json --root inputs
```

Use a Linux AMD64 Docker engine without GPU devices. Pull the three immutable
image inputs in advance, then compile without RUN-step networking:

```sh
docker build --platform linux/amd64 --network none \
  --target frigate-owned724 \
  -f docker/rocm/legacy724/Dockerfile.source \
  -t frigate-local:owned724-candidate .
```

Each build step verifies its inputs before use. It makes no upstream source
changes. The classic LLVM/rocMLIR source build is substantially larger than
layering the existing runtime. The default is two compile jobs. The initial local
run used three jobs in a four-CPU VM. Compilation then moved to an isolated NAS
container with 12 jobs, CPU set `2-7,10-15`, and a 12 GiB memory limit, leaving
CPUs `0,1,8,9` outside the build's CPU set. Both stages exclude GPU devices and
RUN-step networking. The build receipts record the actual resources. Ninja's LLVM
and rocMLIR linker-pool settings are left empty because these old nested CMake
files otherwise append duplicate pools; the linker is selected with
`LLVM_USE_LINKER=lld` rather than `LLVM_ENABLE_LLD` for the same nested-config
reason. Neither adjustment changes the inference source or tuning profile.
The build selects the fat compiler and `GpuModuleToRocdlirTranslation` targets.
The latter is outside the fat compiler's dependency closure but is required by
the project's install rules. Developer executables are not part of this runtime.
CK's JIT-only configuration unconditionally configures a test dependency. Its
declared GoogleTest commit is therefore cached and hash-locked, then supplied
through the supported `GOOGLETEST_DIR` option and explicit
`FETCHCONTENT_SOURCE_DIR_GOOGLETEST` cache override. The latter also replaces an
empty value left by a previous configure attempt. No dependency fetch or GPU
test execution is permitted during compilation.

SQLite 3.50.4 needs its supported `--soname=legacy` option so consumers link to
`libsqlite3.so.0` instead of an absolute path inside the build prefix. The first
strict linking check caught that packaging error. The binding also needs
MIGraphX's private installed include tree, alongside the shared prerequisites'
headers. Debian's offline binding packages are installed together through APT
with repository sources disabled, allowing it to order Python's pre-dependencies
correctly. Package hashes are checked before installation.

The CPython 3.11 binding is built separately on pinned Debian 12, following
Gary's binding approach. The Ubuntu builder's unused CPython 3.10 module is not
shipped. The final image uses the same pinned standard Frigate application and
the same two adapter files as the currently qualified binary-layer recipe.
It does not import any binary from Gary's image or archive. For this run, the
source and binding stages executed in bounded CPU-only Linux containers, then
their outputs were assembled using the public Dockerfile's final stage. The
single-command Dockerfile build above was not separately repeated from scratch.

Qualification must check actual ELF dependencies and native symbol relocations,
binding/application imports, CPU
ORT coexistence, `pip check`, explicit gfx900 HIPRTC compilation on the CPU, and
compilation through MIGraphX's own HIPRTC helper, plus the copied config/database
migrations before any GPU trial. All those checks
run in network-free containers without devices and use disposable appdata.
The arithmetic check runs both the reference target and the oneDNN CPU target,
exercising the rebuilt CPU backend and its packaged OpenMP library.
Even a complete offline pass does not establish fresh model compilation,
inference correctness, performance, or GPU stability. Those require a separately
authorized hardware trial with a recovery plan that does not assume a shared
GPU can be safely reset.

## Maintenance and release lifecycle

The small Frigate adapter and image assembly remain separate from the frozen
runtime source recipe. A Python ABI change requires rebuilding the binding;
changes to the detector contract or config migration require adapter checks.
The full rocMLIR/MIGraphX build does not need to run for every Frigate update
when the runtime inputs and ABI are unchanged.

As checked on 2026-10-20, AMD's
[7.2.4 release notes](https://rocm.docs.amd.com/en/docs-7.2.4/about/release-notes.html)
and [version history](https://rocm.docs.amd.com/en/develop/release/versions.html)
show a superseded release, but no whole-stack 7.2.4 end-of-life date was found.
The named tracing-tool deprecations are not an expiration date for all HIP,
MIOpen, rocBLAS and MIGraphX libraries. Continued package availability does not
promise future bug or security backports. Keeping the verified inputs locally
preserves build availability; it cannot guarantee future host-driver or Python
compatibility. The 5700G is a community compatibility target, not an officially
certified AMD configuration.
