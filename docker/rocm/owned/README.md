# Owned Frigate AMD builds

One entry point builds two pinned runtimes against the same upstream Frigate
application image. The application pin is in application-lock.json; AMD source,
SDK, package, and tool inputs are locked separately.
The common application lock and command-line resource limits are authoritative
for this entry point. Older assessments and application/job metadata in legacy724
describe the earlier prototype.

| Profile | Runtime method | Compatibility changes |
| --- | --- | --- |
| 724 | MIGraphX 2.15, classic rocMLIR API 4, AMD ROCm 7.2.4 packages | Gary's full backend/target profile, gfx900 override, official 6.3.4 gfx900 BLAS kernel data |
| 101 | MIGraphX 2.18, classic rocMLIR API 6, stable AMD ROCm 10.1 SDK, source-built rocBLAS/Tensile | Native gfx90c logic headers, rocBLAS-only lowering guard, CK and hipBLASLt disabled for legacy GCN |

The 10.1 compiler is deliberately the classic implementation. The standard
10.1 ONNX Runtime provider uses a different Triton compiler, which previously
failed for gfx90c. This pipeline does not establish support for that provider.

MIGraphX, classic rocMLIR, and their build dependencies come from pinned source.
The 10.1 rocBLAS/Tensile library is also built from source. HIP, MIOpen, and
other foundational SDK libraries remain pinned AMD binary inputs, as in the
reference approach. Neither profile downloads Gary's compiled MIGraphX asset.
A separate AMD repository or a GitHub release is unnecessary for local builds.

## Build on a Linux amd64 host

The client needs Python 3.9+, SSH, and access to Docker on the selected host.
The host needs Docker, bash, and tar. Use a dedicated SSD workspace and a
private receipt directory outside Git. The config-copy argument must point to
an existing saved backup with its model and label files.

From this repository:

```sh
python3 docker/rocm/owned/pipeline.py all \
  --profile 724 --ssh-host nas \
  --workspace /mnt/ssd/frigate-owned-RUN \
  --receipts /private/frigate-build-receipts \
  --config-copy /private/frigate-config-copy \
  --cpuset 2-7,10-15 --jobs 12 --memory 12g
```

Repeat with --profile 101. Each profile has separate inputs, object caches,
prefix, runtime staging, and receipts beneath the selected workspace.
The defaults reserve logical CPUs 0, 1, 8, and 9 on the target 5700G system.
Set explicit limits for other hosts. Cold compiler builds take substantial time.

Modes are prepare, fetch, build, compiler, assemble, qualify, all, and status.
Networking is available only during acquisition. Compiler and qualification
containers are unprivileged, have no GPU devices, use network none, and have
CPU, memory, and process limits. The final image assembly also uses network none.

The build runs from locked downloads in an empty object/prefix workspace.
Existing verified downloads may be copied into inputs to avoid downloading
them again. Mutable compiler caches must stay separate from other runs.
Re-running the same profile resumes its compiler cache. A client lock prevents
two commands from modifying that profile concurrently.
Use a new workspace for changes to AMD source pins, SDK inputs, or compiler
settings. Existing compiler prefixes are caches for the same pinned recipe.

The command records the Docker engine, exact container/image IDs, input hashes,
stage exits, OOM state, and per-attempt logs. A still-running container with
ExitCode 0 is rejected as incomplete. No command in this entry point stops,
recreates, resets, or deploys a Frigate service.

## Offline checks

The compiler check links a small probe to the same owned classic compiler
archive used by MIGraphX. It generates FP32 and FP16 convolutions for the
profile's explicit architecture. The probe checks ELF machine and architecture
flags; it never loads or launches a GPU kernel.

With config-copy, qualification checks:

- The complete inference library closure, relocations, binding and Frigate imports.
- HIPRTC and MIGraphX's actual runtime compiler helper with an explicit target.
- Reference and oneDNN CPU arithmetic and the real model's ONNX tensor contract.
- Real config/database migrations, preserved camera settings and database rows,
  credentials, backups, integrity, and idempotence, using only the disposable copy.
- Non-root cache/config/database writes, config tests, and detector adapter tests.

Pass --corpus /private/jpeg-directory to also execute the real YOLO26 model on
the CPU using ONNX Runtime and the owned MIGraphX/oneDNN backend. The test uses
Frigate's NCHW/float conversion and its actual YOLO postprocessor. Include
positive object crops as well as negative frames; a corpus with no confident
reference detections is rejected. Inputs, reference tensors and comparisons
are returned in the private qualification archive.

qualify_model.py has a separate GPU mode with an explicit --allow-gpu gate.
It checks the same tensors and all three enabled tuning controls. Cold mode
requires an empty private cache; warm mode requires the prior cold receipt and
matching model/runtime cache hashes. It records full raw outputs, detection
comparisons, initialization time and adapter timing samples. Confident matches
require class agreement, box IoU of at least 0.98 and confidence error at most
0.02; scores around the 0.4 threshold are reported separately. These tolerances
are acceptance limits, not a claim of model accuracy.

Config and model files are copied into a disposable qualification container.
They are absent from the built image. Source backup hashes are checked before
and after qualification. Keep private output archives outside the repository.

These checks establish build and offline compatibility. Hardware acceptance
also requires cold model compilation, numerical comparison on fixed inputs,
isolated performance measurements, cache reload/restart tests, and the actual
camera workload on the target iGPU. Build or parser success alone is insufficient.

gpu_canary.py provides separate hip, blas and convolution steps for an approved
hardware window. The HIP step uses qualified-helper.hsaco from the offline
archive. Run one step at a time and stop progression on failure. The canary checks
SDMA, gfx override and CPU scheduling settings, one HIP kernel, fixed FP32 SGEMM,
and a tiny MIGraphX convolution against CPU arithmetic before the full model.
These commands are never invoked by all or qualify. They contain no service,
GPU reset or reboot operations. A process deadline cannot contain a kernel or
driver fault on a GPU shared with production.

Inside an authorized disposable GPU container, place the harness files together
under /qualification/tools, copy qualified-helper.hsaco from that profile's
offline archive, and extract its corpus-reference directory under
/qualification/reference. Use separate private config/cache copies for the
canary and full-model tests. Run the canary steps individually:

```sh
python3 /qualification/tools/gpu_canary.py hip --allow-gpu \
  --code /qualification/qualified-helper.hsaco --output /results/hip.json
python3 /qualification/tools/gpu_canary.py blas --allow-gpu \
  --output /results/blas.json
python3 /qualification/tools/gpu_canary.py convolution --allow-gpu \
  --output /results/convolution.json
```

After all three pass, run qualify_model.py gpu with --allow-gpu, --model,
--labelmap, --reference /qualification/reference, --cache-policy cold, and a
fresh --output directory. Repeat in a new process with --cache-policy warm and
--cold-receipt pointing to the first result.json. Keep the same model, reference,
runtime namespace, private caches and tuning controls. The result records the
compiled program, numerical comparisons, cache hash and every latency sample.

## What remains to maintain

Ordinary Frigate updates require merging upstream, resolving the two direct
detector adapter files if necessary, updating application-lock.json to the same
official source/image revision, and repeating qualification. They do not require
changing AMD source pins or rebuilding the compiler runtime when its inputs and
Python ABI are unchanged. The 3.11 binding must be rebuilt if Frigate changes ABI.

The application delta remains in frigate/detectors/plugins/migraphx.py and
frigate/detectors/legacy_amd.py. It preserves Gary's tuning controls and YOLO
parser while adapting the current Frigate detector configuration contract.
Native mode retains SDMA=0 without forcing gfx900. Runtime-specific namespaces
keep compiled models, MIOpen data, and COMGR caches apart.

AMD updates require refreshing the corresponding source lock, reviewing its
small compatibility transformations, and repeating both offline and hardware
checks. The 10.1 profile retargets only the architecture header in 46 pinned
Vega 10 logic files; kernel tuning values are preserved and Tensile generates
the gfx90c code. This transformation refuses a changed source layout.

Reproducibility means documented commands, immutable source/package/image
identities, consistent build settings, and independently verified results.
Bit-for-bit binary identity is reported only when measured.

## Resource retention

Input caches and accepted runtime artifacts are intentional rebuild/recovery
material. Compiler objects are scoped to their profile. Retire owned temporary
containers and superseded, unreferenced images by the full IDs in the receipt
after acceptance and after preserving diagnostic output. Running, stopped, and
Created containers protect their image references. Keep persistent appdata,
models, keys, databases, backups, volumes, and shared images. Never use a global
prune or force removal for this workflow.
