# Current Frigate with the working ROCm 7.2.4 stack

Offline feasibility assessment, 2026-10-20. Production and development services
were not contacted or changed. The 10.1 compiler work is on hold.

**The application interface appears compatible with a small legacy detector
adapter. A complete image has not been built or GPU-qualified.** The remaining
work is runtime packaging, dependency provenance, and application migration
checks. No new GPU architecture support is required by the source prototype.
No inference speed improvement is claimed.

## Scope and exact revisions

- Latest upstream `dev`, verified with `git ls-remote` on 2026-10-20:
  [`5bb2cde8b39b682e5b583f224bd58cc9ea975608`](https://github.com/blakeblackshear/frigate/commit/5bb2cde8b39b682e5b583f224bd58cc9ea975608).
  This is 0.19 development, not a stable release designation.
- Working application/runtime source: Gary's Frigate
  `fdeafe9f4c401644f6acc7389e8f406dd241d068`, reproduced by our
  `rocm-7.2.4` branch at `f0ac7282a1ac16e4989dce303dc8df2f428c01d0`.
- Hardware/model contract: Ryzen 7 5700G, existing gfx900 compatibility override,
  the unchanged YOLO26s distilled 320px model, BGR/NCHW/float32, end-to-end
  `(1, 300, 6)` output. Model SHA256:
  `6c2662cd56393e30041cc67ca14b18c20388d7234ebd159b3eb998ec5371197e`.

Both image recipes still use Debian 12, CPython 3.11, and NumPy 1.26. The
repository guidance mentions newer Python, but the inspected image Dockerfile
installs 3.11. The working MIGraphX extension is a CPython 3.11 Linux x86-64
binding. There is no immediate interpreter or NumPy major-version change to
solve; actual Linux linking remains untested for the proposed image.

## Concrete application prototype

`source-prototype.patch` is inert. It adds two files when applied to the pinned
upstream tree and changes no existing application file:

| Added file | Lines | Purpose |
| --- | ---: | --- |
| `frigate/detectors/plugins/migraphx.py` | 321 | Restore Gary's 310-line direct MIGraphX detector, retain its YOLO26 output handling, and add a small tuning-settings bridge |
| `frigate/detectors/legacy_amd.py` | 30 | Preserve the existing APU compatibility helper separately from upstream's unrelated detector utilities |

The functional changes to the old detector are one helper import and a boolean
environment reader used by the three tuning defaults. Inherited detector and
postprocessing logic stays the same. The patch also removes two trailing spaces.
It is a compatibility probe, not production-ready code or a complete image.

Upstream's plugin scanner, `DetectionApi`, device parser, detector factory, and
new dependency lifecycle hooks accepted the restored plugin without shared API
changes. The direct plugin already understands the existing end-to-end output,
so this route does not need the separate `yolo-e2e` enum/parser changes from the
10.1 provider experiment. It must remain configured as `migraphx`, not `onnx`.

Ten CPU-only checks passed against the actual upstream registration/configuration
code and the legacy detector using mock MIGraphX programs. They cover registry
discovery, device/model construction, migration behavior, explicit tuning
settings, invalid settings, compatibility flags, compile/load calls, NCHW data
preservation, and end-to-end output mapping. They do not compile or execute a
GPU program, load vendor libraries, or prove full application compatibility.

## Configuration work we must retain

Upstream replaces `detectors:` plus `model:` with `models:` and device strings.
Its generic migration carries over the model fields and `migraphx:GPU`, but
discards `conserve_cpu`, `fast_math`, and `exhaustive_tune`. Reconstructing the
unmodified old detector config makes `exhaustive_tune` false, whereas the saved
working configuration explicitly sets it true. This was reproduced in the
CPU-only audit.

The prototype keeps these settings in the plugin, avoiding a new shared model
schema or config migration patch. The proposed image/deployment profile must
explicitly set:

```text
FRIGATE_MIGRAPHX_CONSERVE_CPU=1
FRIGATE_MIGRAPHX_FAST_MATH=1
FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE=1
```

The reader accepts only `0` or `1` and rejects invalid values during device
configuration, before detector initialization. These environment settings apply
to this legacy detector profile. They are not per-model tuning controls.

`example-model.yaml` shows the proposed model block. It is not a replacement
for the private camera configuration. Preserve the camera workload, normalization,
masks, zones, thresholds, and VAAPI configuration. Dev recording remains off,
including any explicit camera-level overrides. Upstream may rename detector
statistics from the old `rocm` alias to its generated device name.

Upstream's hardware discovery currently advertises AMD as `onnx`, even when this
legacy plugin is installed. Explicit `devices: [migraphx:GPU]` works at the
configuration interface. For correct automatic selection in the hardware UI, a
small conditional in `frigate/detectors/hardware.py:detect_amd_gpu` should prefer
`migraphx:GPU` when that plugin is present. That optional UI integration is not
implemented or tested by this prototype.

## Runtime package we would own

Use current upstream's ordinary application/dependency stages, then add a
separately versioned legacy runtime. Do not use upstream's ROCm 10.1 stage or
copy the old image's application, nginx, s6 services, or frontend wholesale.

The existing baseline recipe is the starting point for these owned files:

| Proposed file or artifact | Responsibility | When it needs attention |
| --- | --- | --- |
| `docker/rocm/legacy724/Dockerfile` | Assemble the old ROCm libraries, MIOpen database, gfx900 rocBLAS kernels, Python binding, loader paths, Mesa/OS dependencies, and compatibility environment | Initial packaging, then base-image or Python ABI changes |
| `docker/rocm/legacy724/CMakeLists.txt` | The existing 36-line binding build linked to MIGraphX core/ONNX/TF libraries | Python, pybind11, or MIGraphX ABI changes |
| A dedicated Bake target | Combine current upstream `deps` and `rootfs` with the frozen legacy package, preserving the upstream image build | Upstream Docker target changes |
| A runtime lock/manifest and retained package bundle | Exact source commits, package versions, URLs, SHA256 values, and expected library identities | Deliberate runtime changes or dependency rebuilds |
| An owned MIGraphX dependency build recipe | Reproduce the gfx900-enabled 2.15 runtime instead of relying indefinitely on Gary's release asset | One-time ownership work, then deliberate runtime changes |
| Adapter and regression tests | Preserve the model contract, tuning policy, compile/cache behavior, and new config construction | Frigate detector/config changes |

These packaging files are a maintenance specification; no complete packaging
patch or frozen runtime bundle was produced in this assessment. Normal Frigate
updates should reuse that bundle rather than rebuild AMD compilers each time.

The working runtime environment must retain:

```text
HSA_ENABLE_SDMA=0
HSA_OVERRIDE_GFX_VERSION=9.0.0
MIGRAPHX_DISABLE_MIOPEN_FUSION=1
MIGRAPHX_DISABLE_SCHEDULE_PASS=1
MIGRAPHX_DISABLE_REDUCE_FUSION=1
MIGRAPHX_ENABLE_HIPRTC_WORKAROUNDS=1
MIOPEN_CUSTOM_CACHE_DIR=/config/model_cache/migraphx
MIOPEN_USER_DB_PATH=/config/model_cache/migraphx
AMD_COMGR_CACHE=1
AMD_COMGR_CACHE_DIR=/config/model_cache/migraphx
```

Preserve `/opt/rocm` and its library/header layout, `ld.so.conf` paths, and the
matching C++ runtime/development headers used by HIPRTC. Upstream now runs
services without root by default and has built-in `/dev/kfd` and `/dev/dri`
access handling. Validate device and cache permissions in a future candidate;
this does not require a new AMD driver or a host configuration change.

## Existing dependency ownership gaps

The 7.2.4 reproduction currently pins two Gary binaries by hash:

| Input | Current source and identity | Remaining ownership issue |
| --- | --- | --- |
| MIGraphX archive | Gary's `migraphx-v7.2.4-1.29.0.tar.gz`, SHA256 `633279fbd5a1f7f16b9e60cfca312418890d66befbbcec60fe1067f739719882` | It is a Gary-hosted binary; we have not reproduced this exact asset from recorded build inputs |
| ORT MIGraphX wheel | `onnxruntime_migraphx-1.29.0-cp311-cp311-linux_x86_64.whl`, SHA256 `fc4959eec9468e0c66840d9bdb7b44439e661baa849976a5675e0a0160fdaa71` | Installed by the old image recipe, although the direct object detector never imports ORT |
| ROCm libraries | AMD `/apt/7.2.4/`, Jammy package repository | Package builds and hashes are not locked in the old Dockerfile |
| gfx900 rocBLAS kernels | AMD `rocblas_4.3.0.60304-76~22.04_amd64.deb` from ROCm 6.3.4 | Filename is pinned, archive SHA256 is not |
| MIGraphX Python binding source | AMD `rocm-7.2.4`, `.3`, then `.2` tag fallback | Replace the fallback download with one verified commit/hash |

The archive's `1.29.0` suffix is an ORT variant, not the MIGraphX version.
The source and loaded SONAME identify MIGraphX **2.15.0**.

Gary's AMDMIGraphX tag `v7.2.4` resolves to
[`6e8f5f6e1250a387454087e98519cc5c28350be8`](https://github.com/garymathews/AMDMIGraphX/commit/6e8f5f6e1250a387454087e98519cc5c28350be8).
Against AMD's `rocm-7.2.3` commit
`07ef4ba4f9ef95d241b7be165e60ad148f3344ee`, the three extra commits change
build/CI files and an ORT test pin. They change no MIGraphX `src/` implementation.
The recipe adds `gfx900` to `GPU_TARGETS` and pins classic rocMLIR
`6671a1ee31d44e1f2f7743a26a71ffc4ce9169bf` (source version 2.0.0), plus
Composable Kernel, oneDNN, and msgpack dependencies. This is a dependency build
to reproduce and pin, not evidence that we need to port a compiler backend.

There is a provenance gap: the checked tag/workflow defaults to ORT 1.26.0,
while the consumed asset says 1.29.0. Its exact build inputs are not established
by that tag. A hash preserves an asset's identity but does not prove how it was
built. An owned rebuild must be checked against the working baseline; identical
performance or cache compatibility cannot be assumed.

For the current workload, semantic search, face recognition, LPR, and bird
classification were disabled in the saved config. The proposed smallest path
keeps upstream's ordinary CPU ORT for those separate features and uses direct
MIGraphX only for object detection. This avoids maintaining a custom ORT wheel
if Linux linking and application checks confirm it can be omitted. GPU
acceleration for those enrichments would be separate scope.

## Repeating the offline check

From this source tree with the CPU audit dependencies installed:

```sh
python3 -u docker/rocm/legacy724/test_source_compatibility.py
```

Use CPython 3.11 and `audit-requirements.txt` for the recorded environment. The
script copies the Python package to a temporary directory and applies the
prototype there. It leaves the checkout's application files untouched. Only
the CPU and legacy detector plugins are selected for this focused test;
optional native runtimes are stubbed or blocked. During tests, native library
loads, subprocesses, and network connections are blocked. Mock objects stand
in for every MIGraphX GPU call.

The next bounded work is a Linux image build without GPU devices: verify
library linking, dependency consistency, full copied-config validation, and
database migration on disposable copies. GPU testing and a dev deployment are
outside this offline assessment. No production changes, GitHub publication, or
10.1 compiler work is authorized by this document.
