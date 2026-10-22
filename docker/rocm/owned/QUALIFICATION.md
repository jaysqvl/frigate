# Qualification record, 2026-10-22 UTC

Both source pipelines pass offline qualification, full-model target-GPU
numerical checks, the balanced warm comparison and the five-camera trials.
Production and the existing development service have been restored to their
original builds. Owned 7.2.4 closely matches Gary's measured latency; native
10.1 works on gfx90c but is slower and carries an extra BLAS source-build step.

The common upstream pin is 91e91c68efe504e17b7fd3fb437b34068b4387ca,
application version 0.19.0-91e91c6. The build implementation is local commit
dda519dc7e11546823d79b4bd2f13d381673ee17. No release or registry publication
was needed. Follow [README.md](README.md) to run the pipelines.
The upstream dev ref was checked again on 2026-10-22 at 13:41 UTC and still
matched the tested application pin.

## Build and offline evidence

| Check | 7.2.4 | Native 10.1 |
| --- | --- | --- |
| Independent build from empty object/prefix directories on Linux amd64 | Passed | Passed |
| Locked inputs, compile network disabled, no GPU devices | Passed | Passed |
| Source, Python binding, image assembly | Passed | Passed |
| Classic compiler, explicit FP32 and FP16 convolution code generation | gfx900 passed | gfx90c passed |
| Actual runtime HIPRTC helper | Passed | Passed, including its chunked MessagePack reply |
| Native library/helper checks | 30, zero unresolved dependencies | 112, zero unresolved dependencies |
| Standalone symbol relocation checks | 29 passed | 111 passed |
| Frigate import, binding import, CPU ORT coexistence, pip check | Passed | Passed |
| Full YOLO26s-distilled CPU inference against CPU ONNX Runtime | 19 fixed images passed | Same 19 images passed |
| Real copied config/database migration and non-root writes | Passed | Passed |
| Linux config, adapter and helper-protocol tests | 24 + 14 + 2 passed | 24 + 14 + 2 passed |

Builds used logical CPUs 2-7,10-15, 12 jobs and a 12 GiB memory limit. Only
immutable downloads were shared with the independent builds. The 10.1 BLAS
package contains 99 source-generated gfx90c code objects; both plain ELF objects
and compressed LLVM offload bundles were inspected for the actual target ISA.

The unchanged model contract is BGR/NCHW/float32 divided by 255, input
(1,3,320,320), output (1,300,6). Conserve CPU, fast math and exhaustive tuning
are enabled for both profiles. The corpus includes six confident reference
detections. These are arithmetic/parity checks, not model-accuracy ground truth
or a replay of the application's motion-region selection.

Copied 0.18-0 configuration migrates to 0.19-0 while preserving all five camera
workloads, streams, model and tuning. Database migrations 036-039 preserve the
old rows, columns and login records; integrity, foreign keys, exact backup and
second-run idempotence pass. Recording is disabled. The source backup is
unchanged, and no live appdata or recording array was mounted in these tests.

## Measured reproducibility

The independent 7.2.4 runtime has identical SHA256 content for all 8,878 regular
files and identical targets for all 1,105 symlinks compared with the earlier
owned build. Its classic compiler archive and Python binding also match.

The 10.1 trees contain the same 28,992 regular-file paths and 1,177 symlink
targets. Every native library, compiler archive and kernel matches. Four files
differ: the CMake cache's type annotation for the same C++ compiler path, the
new code-object inspection metadata, and timestamps in two Python bytecode
cache headers. The Python bytecode payloads match. This is not a claim of
bit-identical Docker images or complete 10.1 runtime archives.

Standalone runtime archives are integrity-tested and hash-verified on both the
build host and client, outside Docker writable layers:

| Profile | Archive SHA256 | Bytes |
| --- | --- | --- |
| 7.2.4 | 0104f8dc00616ea13b964847cec0f299516f7d2b2f5912e14c73358e4b23fa24 | 1,595,748,707 |
| 10.1 | ab3cd1b27390449bdf3de1374d402e77f5c1836c5f3c1daf90841d1c7856738d | 1,778,151,953 |

## Maintained compatibility

The 7.2.4 pipeline reproduces Gary's documented source/backend approach. Exact
build provenance for his distributed binary is unavailable, so equality with
that release asset is not asserted. The owned builds consume pinned AMD SDK
binaries for foundational components, and compile MIGraphX, classic rocMLIR and
their dependencies from source. The 10.1 profile additionally compiles
rocBLAS/Tensile. Neither pipeline consumes Gary's compiled MIGraphX payload.

The 10.1 profile deliberately uses classic rocMLIR API 6. It does not qualify or
fix the standard 10.1 ONNX Runtime provider's Triton compiler. Neither profile
is certification of the entire ROCm SDK or every GPU/model combination.

Relative to the common upstream pin, the application carries two adapter files:
the 377-line direct MIGraphX detector and a 39-line AMD environment helper. Much
of the detector is the carried Gary implementation. These are application
maintenance, alongside the separate build recipes, locks and qualification
tools; the total repository addition is larger than a small AMD source patch.

| Maintenance item | 7.2.4 | Native 10.1 |
| --- | --- | --- |
| MIGraphX / classic rocMLIR API | 2.15 / 4 | 2.18 / 6 |
| AMD source patch files | None | One lowering guard, +5/-1 lines |
| BLAS support | Pinned official 6.3.4 gfx900 kernel data with the 7.2.4 SDK | Source-built rocBLAS/Tensile, architecture headers retargeted in 46 pinned Vega 10 logic files |
| GPU selection | gfx900 override | Native gfx90c, no override |
| MLIR / CK / hipBLASLt build settings | On / on / on | On / off / off |
| Recorded independent source-build stage | 5,171.9 s, about 86 min | 3,631.2 s, about 61 min |

Both use the same pipeline.py entry point. Build times are observations, not a
controlled build-speed comparison: the target/backend sets differ. Ordinary
Frigate updates can reuse the frozen AMD runtime and matching model cache while
the Python ABI, model weights and compilation settings remain compatible.
Review the two adapter files and refresh the application lock, then repeat
qualification. AMD pin changes require rebuilding and retesting that profile.
The 7.2.4 recipe also retains Gary's correction for an obsolete absolute librt
path in MIOpen's imported CMake link metadata; it does not patch MIOpen source.

The private hardware-window coordinator passed 21 CPU-only fault simulations:
preflight rejection, successful completion, test failure, timeout, partial
original-service shutdown, unconfirmed test shutdown, failed original-service
restart, and failed health/API readiness. It preserves failed-test exit codes
and refuses to restart the originals beside an unconfirmed running test.
A separate real GNU timeout check terminated a TERM-ignoring child. The
simulations use fake Docker/API responses and accelerated readiness deadlines;
they do not prove real GPU containment, restoration time or driver recovery.

## Target-GPU correctness

The same application pin, YOLO26s-distilled model and 19-input corpus were used
for both owned builds and a Gary-runtime control. Conserve CPU, fast math and
exhaustive tuning stayed enabled. The control uses Gary's existing runtime
with the common newer application, rather than a different application version.
Each test used logical CPUs 2-7,10-15, 12 GiB memory, isolated private caches,
SDMA disabled, and exclusive access to the target iGPU while the original
services were stopped. No recording array was mounted.

| GPU check | Gary control | Owned 7.2.4 | Native 10.1 |
| --- | --- | --- | --- |
| HIP one-element kernel, 41 to 42, scheduling flag 4 | Passed | Passed | Passed |
| FP32 64x64 SGEMM, maximum absolute error | 5.72e-6 | 5.72e-6 | 5.72e-6 |
| Tiny convolution, maximum absolute error | 1.91e-6 | 9.54e-7 | 1.91e-6 |
| Full YOLO26s GPU comparison, 19 fixed inputs / six confident matches | Passed | Passed | Passed |
| Minimum matched box IoU | 0.99999926 | 0.99999913 | 0.99999864 |
| Maximum matched confidence error | 8.34e-7 | 4.17e-7 | 5.96e-7 |

The model SHA256 is
6c2662cd56393e30041cc67ca14b18c20388d7234ebd159b3eb998ec5371197e.
All processes used scheduling flag 4 and enabled conserve CPU, fast math and
exhaustive tuning. Native 10.1 passed without HSA_OVERRIDE_GFX_VERSION. The
test harness enforces SDMA=0 before loading GPU libraries. These detection
comparisons use the stated thresholds; raw output rows are not asserted to
have identical ordering.

## Isolated warm performance

The accepted sequence was Gary, 7.2.4, 10.1, 10.1, 7.2.4, Gary. Each fresh
process loaded its own successfully compiled, hash-matched cache, executed
20 warmups, and timed 100 calls at 5 Hz on the same fixed tensors. Timing covers
the actual adapter input copy, synchronized inference and postprocessing.
Production and existing development were stopped throughout this sequence.

| Runtime | Pooled median, 200 calls | p95 | Change in median versus Gary | Separate process medians |
| --- | --- | --- | --- | --- |
| Gary control | 15.99 ms | 16.77 ms | Reference | 16.00 / 15.98 ms |
| Owned 7.2.4 | 16.16 ms | 16.92 ms | +1.08% | 16.14 / 16.18 ms |
| Native 10.1 | 17.30 ms | 17.96 ms | +8.21% | 17.21 / 17.42 ms |

Native 10.1 was 7.06% slower than owned 7.2.4 by pooled median. This batch
shows no inference-speed improvement from moving this model to 10.1. Two
process repeats provide a descriptive comparison, not a formal confidence
interval or a long-duration reliability result. Read-only telemetry recorded
31-39 C; clock policy was not changed.

Observed cache-load times were 4.11/4.26 s for Gary, 12.23/4.26 s for owned
7.2.4, and 2.81/2.82 s for native 10.1. Initial exhaustive compilation required
interrupted/resumed windows for all three; those histories are preserved.
The final resumed constructor times are partial work and are not fresh-cold
startup benchmarks. Five-minute windows lost unfinished candidate-generation
work until longer windows and completed-choice persistence were available.

The newer MIGraphX tuner uses adaptive candidate benchmarking; the older one
uses 10 bundles of 20 evaluations. All compiled listings contain 39
convolution instructions and 62 generated-code lines with MLIR symbols. Gary
and owned 7.2.4 have the same operator histogram. Native 10.1 has a different
listing and a larger scratch allocation (20,513,600 versus 7,160,000 bytes).
These are structural observations, not attribution of the measured slowdown
to a particular kernel or compiler choice.

## Camera workload and test-history limits

The copied production appdata configuration differs only by recording disabled
globally and for all five cameras. Weights, streams, model input contract,
motion settings and detection rates are preserved. Camera trials use private
config/database/model-cache copies, actual camera streams, the production
VAAPI driver setting and a tmpfs media directory. No recording-array mount is
present. Readiness requires completed detector activity, rather than the idle
10 ms placeholder, followed by 16 fresh statistics snapshots and a stable
detector PID. Database integrity/foreign keys and zero recording video files
are checked before deliberate shutdown.

Both trials passed all 16 updates over 242 seconds of fresh statistics, with
at least 5.0 process fps for every camera, stable detector PIDs, database
quick_check=ok, zero foreign-key violations and zero recording videos.

| Camera-workload observation | Owned 7.2.4 | Native 10.1 |
| --- | --- | --- |
| Detector latency reported by live statistics, median | 16.47 ms | 18.19 ms |
| Reported detector latency range | 16.02-16.89 ms | 17.63-19.29 ms |
| Minimum camera process fps | 5.0 | 5.0 |
| Window including original-service restoration | 354 s | 371 s |

These live values are application statistics from sequential camera activity,
not the controlled fixed-input timing samples above. Recording was deliberately
disabled, so the candidate builds' recording paths were not qualified here.

Failed attempts remain in the private record. The first warm sequence stopped
when the GPU-isolation guard observed a transient render-node holder before
the third worker; its two completed timing runs are excluded. The full balanced
sequence was repeated successfully. The first camera trial used JSON text in
a .yaml copy; CPU-only reproduction proved that go2rtc rejected the generated
flow-style YAML. Semantically identical block YAML registered all eight streams
and corrected the trial without changing a runtime image. The successful 7.2.4
workload then hit a controller-only exit-status check after intentional SIGTERM
returned 143. Its complete S6 shutdown, pre-stop health and passed observer were
reviewed explicitly; the original nonzero controller receipt is preserved.
Intentional application stops now accept 0 or 143; model workers still require 0.

One early extended Gary tuning window reached its 1,800-second readiness limit
before every camera had resumed. A separate follow-up verified both unchanged
original services and all five camera pipelines without a reset or reboot.
Later extended windows reserve four minutes for restoration. The accepted warm
comparison, including restoration, took 250 seconds.

The final application checks verify the exact original container IDs, images,
definitions, mounts, static configuration and model hashes, plus three samples
with all five cameras processing on each original service. Development recording
remains disabled and production recording retains its original setting. No new
matching critical GPU/kernel errors were found and the boot ID is unchanged.
No GPU reset, driver unload or reboot was performed.

This qualifies the tested hardware/model/profile combination. It does not
certify every ROCm component, model, GPU or long-running deployment. Historical
offline receipts retain their original CPU-only status; subsequent hardware
receipts identify the exact images qualified here. Permanent deployment and
test-resource cleanup are separate from these measurement results.

## Completion and retention

The final cleanup removed 21 recorded test/prerequisite containers and the
unreferenced Gary control image, with no cleanup errors. Three disposable
application/model-cache copies were retired after archiving their configuration,
database and generated keys privately. The device-free formatting probe and
temporary camera environment file were also retired. Earlier cleanup receipts
remain part of the history. No global prune, force image removal, volume
deletion or manual Docker/Btrfs storage deletion was used.

The two accepted owned images, standalone runtime archives, source/input caches,
learned model/tuning caches, private receipts and protected original appdata
remain available. The running production/development containers were not
replaced, and no GitHub release or registry publication was created.
