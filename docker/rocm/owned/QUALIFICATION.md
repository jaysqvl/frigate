# Qualification record, 2026-10-21 UTC

Both source pipelines pass offline qualification. Hardware qualification is
pending. Neither candidate has been deployed or accepted for GPU inference.
The production and existing development services retain their original builds.

The common upstream pin is 91e91c68efe504e17b7fd3fb437b34068b4387ca,
application version 0.19.0-91e91c6. The build implementation is local commit
dda519dc7e11546823d79b4bd2f13d381673ee17. No release or registry publication
was needed. Follow [README.md](README.md) to run the pipelines.

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

## Scope and remaining proof

The 7.2.4 pipeline reproduces Gary's documented source/backend approach. Exact
build provenance for his distributed binary is unavailable, so equality with
that release asset is not asserted. The owned builds consume pinned AMD SDK
binaries for foundational components, and compile MIGraphX, classic rocMLIR and
their dependencies from source. The 10.1 profile additionally compiles
rocBLAS/Tensile. Neither pipeline consumes Gary's compiled MIGraphX payload.

The 10.1 profile deliberately uses classic rocMLIR API 6. It does not qualify or
fix the standard 10.1 ONNX Runtime provider's Triton compiler. Neither profile
is certification of the entire ROCm SDK or every GPU/model combination.

Remaining acceptance is staged target-GPU execution, full-model correctness,
cold/warm cache reloads, isolated balanced performance measurements, and the
actual five-camera workload with recording disabled. The test harness enforces
SDMA=0 and rejects an inherited gfx900 override in native mode. No GPU reset or
NAS reboot is part of the test flow. Offline success alone does not establish
GPU safety, correctness, speed or production readiness.

The private hardware-window coordinator passed 18 CPU-only fault simulations:
preflight rejection, successful completion, test failure, timeout, partial
original-service shutdown, unconfirmed test shutdown, failed original-service
restart, and failed health/API readiness. It preserves failed-test exit codes
and refuses to restart the originals beside an unconfirmed running test.
A separate real GNU timeout check terminated a TERM-ignoring child. The
simulations use fake Docker/API responses and accelerated readiness deadlines;
they do not prove real GPU containment, restoration time or driver recovery.
