# Current Frigate with the frozen ROCm 7.2.4 runtime

Offline Linux qualification completed on 2026-10-20. The candidate combines
upstream Frigate `0.19.0-5bb2cde` with the working MIGraphX 2.15.0 / ROCm 7.2.4
runtime and Gary's direct detector. Library loading, copied configuration,
and copied database checks passed. GPU execution and camera operation remain
unqualified. Production and dev were not contacted or changed. The 10.1 compiler
work remains on hold.

## Exact build and what we own

The local image is `frigate-local:upstream-5bb2cde-rocm724`, immutable image ID
`sha256:2d1693412060ef1f2cfbe3b2d45e3e5ab5ce46d76c679be6e7d1b216539f33c8`.
It was built for Linux AMD64 in a dedicated local VM with no GPU devices. Public
image pulls used the network; all build RUN steps and qualification containers
had networking disabled. No camera processes, Frigate server, ROCm hardware
probe, GPU target, or GPU compiler was started.

The Dockerfile assembles two immutable inputs recorded in `runtime-lock.json`:

1. Official standard Frigate image for upstream
   [`5bb2cde8b39b682e5b583f224bd58cc9ea975608`](https://github.com/blakeblackshear/frigate/commit/5bb2cde8b39b682e5b583f224bd58cc9ea975608).
   It supplies the current application, frontend, OS, and Python dependencies.
   The actual version and five application/migration source hashes were checked
   against this checkout. This is the 0.19 development branch.
2. Gary's frozen 7.2.4 image. We copy its `/opt/rocm-7.2.4` runtime, CPython 3.11
   binding, GCC 14 support headers/files, NUMA library, and OpenMP library. Its old
   Frigate application, frontend, init services, and custom ORT wheel are not
   copied. The image retains upstream CPU ONNX Runtime 1.30.0.

The build does not rebuild AMD compilers. We own the application adapter and
container assembly. Gary's runtime binary remains an external dependency pinned
by immutable image digest. Reproducing that dependency from our own source build
is separate ownership work, with the existing source-provenance gap still open.

| Maintained file | Responsibility |
| --- | --- |
| `frigate/detectors/plugins/migraphx.py` | Restore the direct detector, preserve YOLO26 output handling, bridge three tuning defaults to environment values |
| `frigate/detectors/legacy_amd.py` | Keep the existing APU compatibility helper separate from upstream detector utilities |
| `docker/rocm/legacy724/Dockerfile` | Layer the frozen runtime onto the current standard application image and retain compatibility flags |
| `docker/rocm/legacy724/runtime-lock.json` | Record exact input image digests, ABI, binding and OS-library hashes |
| `docker/rocm/legacy724/offline_checks.py` | Repeat actual Linux linking, copied-config, copied-DB, and permission checks |
| `docker/rocm/legacy724/test_source_compatibility.py` | Ten detector-interface tests using fake GPU objects |

These are **two added application files and no edits to existing upstream
application files**. The previous inert `source-prototype.patch` has been applied
and retired to avoid maintaining duplicate source. The imported detector was
formatted; inherited inference and output-processing behavior was retained.

## Qualification results

| Check | Result |
| --- | --- |
| Runtime binding identity | Matches the saved working CPython 3.11 binding SHA256 exactly |
| Shared library dependencies | 39 native libraries inspected; inference dependencies resolve; four inherited optional-component omissions are documented below |
| Actual imports | MIGraphX binding and full Frigate application import together successfully |
| Dependency consistency | `pip check` passes; CPU ORT 1.30.0 coexists with direct MIGraphX |
| Compatibility environment | SDMA disabled, gfx900 override and all four existing MIGraphX workarounds present |
| Actual copied config | 0.18-0 to 0.19-0 migration and full validation pass, with camera/network probes blocked |
| Model and cameras | Existing YOLO26s distilled 320px model, all five workloads, stream settings, masks/zones, tuning, and recording-off state preserved |
| Config idempotence | Second load makes no further config changes |
| Actual copied database | Migrations 036 through 039 pass; every old column value and row, including login records, remains unchanged |
| DB integrity and backup | Integrity and foreign-key checks pass; startup-created backup matches the original bytes |
| DB idempotence | Second startup migration leaves the DB bytes unchanged |
| Existing export migration | Its saved completion marker is retained; no media files are mounted or processed |
| Non-root writes | UID 1000 can migrate config/DB and write the copied model-cache directory |
| Regression tests | 24 upstream config migration tests and 10 detector-interface tests pass in the Linux candidate |

The private source config and database were hashed before and after and remained
unchanged. Migrated copies and their automatic backups were saved privately
before temporary containers were removed. `assessment.json` is the sanitized
receipt. No GPU performance or inference-correctness claim follows from these
CPU-only checks.

### Packaging details found during linking

The standard image lacks NUMA/OpenMP libraries needed by the frozen runtime.
The Dockerfile copies the exact versions from Gary's image instead of resolving
new apt packages. OpenMP's unversioned `libomp.so` alias is installed in the
normal system library directory; Gary's image had the file only under LLVM 19
while its loader configuration referenced LLVM 14. This also resolves the
previously unresolved oneDNN/MIGraphX CPU-library dependency.

Gary's stripped runtime already contains four optional components with missing
libraries. The candidate preserves them and the checker allows only this exact
baseline set:

| Optional component | Missing dependency |
| --- | --- |
| `libhiprand.so.1.1.70204` | `librocrand.so.1` |
| `libhipsparse.so.4.2.0.70204` | `librocsparse.so.1` |
| Unused Python 3.10 binding | `libpython3.10.so.1.0` |
| `librocprofiler64.so.2.0.70204` | `libhsa-amd-aqlprofile64.so.1` |

These are outside the linked MIGraphX inference-library closure. This
qualification does not certify those optional tools. No additional missing
library is accepted. Actual GPU initialization, compiled-cache reuse, device
permissions, inference output, and live camera behavior still need a separately
scoped hardware test.

## Configuration and model contract

Upstream migrates `detectors:` plus `model:` into `models:`. The resulting device
must be `migraphx:GPU`. The `example-model.yaml` fragment shows the required model
fields; it does not replace the private camera configuration.

The unchanged model is BGR/NCHW/float32, 320 by 320, with end-to-end `(1, 300, 6)`
output. Its SHA256 is
`6c2662cd56393e30041cc67ca14b18c20388d7234ebd159b3eb998ec5371197e`.
The old alias `rocm` becomes the upstream-generated `migraphx:GPU` statistics name.

The generic config migration drops the old detector's tuning fields. The image
sets these to preserve the saved working profile:

```text
FRIGATE_MIGRAPHX_CONSERVE_CPU=1
FRIGATE_MIGRAPHX_FAST_MATH=1
FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE=1
```

Values must be `0` or `1`. They apply to this legacy detector profile, rather
than per-model settings. Runtime compatibility settings remain:

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

Upstream's automatic AMD hardware selection still advertises `onnx`. The explicit
migrated `migraphx:GPU` configuration is validated. No hardware-discovery UI
patch is included. Semantic search, face recognition, LPR, and bird classification
were disabled in the saved configuration; their GPU acceleration is outside
this direct-detector profile.

## Repeating and maintaining the build

Use a local Linux AMD64 Docker engine with sufficient image-layer scratch space.
The first build on the recorded two-CPU VM took about nine minutes; the packaging
follow-up reused the frozen layers and took eleven seconds.

```sh
docker build --platform linux/amd64 --network none \
  --file docker/rocm/legacy724/Dockerfile \
  --tag frigate-local:upstream-5bb2cde-rocm724 .
```

For offline qualification, override the image entrypoint, use `--network none`,
expose no devices or host media, and set `FRIGATE_OFFLINE_CHECK=1`. Copy this
folder's checker scripts into the same path under `/opt/frigate`, and provide a
writable, disposable `/config` owned by UID 1000, including the actual model and
labels. Preserve the already-completed `.exports` marker from saved appdata.
Run from `/opt/frigate` as UID 1000:

```sh
python3 docker/rocm/legacy724/offline_checks.py linking
CONFIG_FILE=/config/config.yaml python3 docker/rocm/legacy724/offline_checks.py migrations
python3 -u -m unittest frigate.test.test_config_migration
python3 -u docker/rocm/legacy724/test_source_compatibility.py
```

The migration command deliberately rewrites the disposable config/DB. Keep
originals outside the container, preserve its private migration outputs, then
retire its temporary container by full ID. No running Frigate service is needed.
The checker refuses exposed GPU devices or a network default route.

For an application update, refresh the pinned standard image, upstream identity
labels/lock and checker version expectation; keep the legacy runtime frozen,
review detector/config API changes, and repeat these copied-data checks. A Python
ABI or C++ runtime change may require rebuilding the binding. An AMD compiler
rebuild is unnecessary for ordinary Frigate-only updates on the current ABI.

For runtime provenance and the previous source assessment, see the parent
assessment commit `a18953eaf542c15cff67eba0559b09aa28c9e7ce`. Gary's 2.15.0 archive
is the `migraphx-v7.2.4-1.29.0` variant: its filename suffix identifies an ORT
variant, not the MIGraphX version. Exact reproduction of that binary from owned
build inputs remains unverified.
