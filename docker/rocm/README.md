# Vega image builds and isolated development

The `rocm-7.2.4` branch reproduces Gary Mathews' Frigate application and GPU
runtime combination from commit `fdeafe9f4c401644f6acc7389e8f406dd241d068`.
The application starts from that exact commit, rather than combining a Frigate
upgrade with the runtime reproduction.

The baseline retains Gary's MIGraphX detector, YOLO26 output handling, tuning
options, ROCm 7.2.4 packages, gfx900 kernels from ROCm 6.3.4, and ONNX Runtime
1.29.0. Its MIGraphX archive and ONNX Runtime wheel still come from Gary's
repositories, with their SHA256 digests checked during installation. Building
these dependency artifacts in this fork is a separate ownership step.

The image is a source reproduction, not a claim of byte-for-byte identity with
Gary's previously published image. Apt repositories and inherited dependencies
can change. The generated Frigate version and OCI revision identify this fork's
build commit.

## Build and publication

Pushes to `rocm-7.2.4` run the AMD64-only image workflow. The workflow can also be
dispatched manually. It publishes these tags to `ghcr.io/jaysqvl/frigate`:

- `<short commit>-rocm-7.2.4`
- `candidate-rocm-7.2.4`

Use the resulting immutable registry digest for deployment. A successful image
build does not establish that GPU inference works on the target machine.
The build metadata is retained as a workflow artifact.

Common dependencies and web assets use the registry cache tags `cache-deps`
and `cache-rootfs` so both branches can reuse them. Each runtime has a separate
`cache-<branch>` tag. These are build caches, not runnable deployment images.
Existing GitHub Actions branch caches are imported when available; new caches
are exported to the registry. A failed cache export warns without failing an
otherwise successful image publication.

The `rocm-10.1-gfx90c` experiment uses a separate branch and candidate tag. Its
Frigate application should remain at the same baseline while the runtime is
qualified, so inference results can be compared without an application upgrade.

## Native gfx90c experiment

The experiment pins all four AMD SDK components and their metapackage to
`10.1.0a20260910`, the same published ROCm 10.1 nightly. The stable 10.1 index does
not publish gfx90c device wheels. This image therefore uses a prerelease SDK,
not a claim of supported stable 10.1 hardware compatibility.

MIGraphX 2.18.0 is compiled from AMD commit
`95672916ed289d4be9d230a9be732e1bbad97e8c` with `GPU_TARGETS=gfx90c`. The build
disables hipBLASLt, Composable Kernel, rocMLIR, and the CPU backend. MIOpen and
rocBLAS remain enabled. It contains no gfx900 override or copied 6.3.4 kernels.
`FRIGATE_ROCM_NATIVE_GFX90C=1` prevents the detector's legacy APU helper from
silently setting an architecture override and rejects a conflicting override.

The SDK and MIGraphX build independently of the Frigate dependency stages so a
Frigate change does not force a GPU compiler rebuild. Both use Debian 12 and
Python 3.11. The SDK's expanded development tree stays in this experimental image to
preserve its vendor-relative library links and runtime compiler headers. The
installed package URLs and archive digests are recorded in
`/opt/rocm-native-package-report.json`; the MIGraphX source revisions and archive
digests are under `/opt/migraphx/share/frigate/`.

Only direct MIGraphX object detection is being qualified on the GPU. ONNX Runtime
1.29.0 is installed without a GPU provider, so ONNX enrichments use the CPU in
this experiment. Native GPU support for those enrichments is separate work.

Use a separate cache directory from the 7.2.4 image, even when the ONNX file is
identical. Do not load the older image's compiled `.mxr`, MIOpen, or COMGR caches.

`/opt/frigate/qualify_gpu.py` performs one warmup and at most 20 measured
inferences on a supplied image or zero tensor. It preserves the BGR/NCHW/float
320px contract and reports model/input hashes, compile time, inference times,
and detections as JSON. Run it with a fresh, isolated `/config` mount, the copied
model and label map, GPU device access, a memory limit, and a command timeout.
Pass `--raw-output /network-output.npy` to save the raw network output from
one additional inference for numerical comparison against the CPU reference.
Copy that file out before retiring the qualification container. A tmpfs output
path disappears when the container stops.
Use the identical script and input for both runtimes. A zero tensor checks
execution only; output agreement on a fixed camera image is not a ground-truth
accuracy evaluation.

## Development deployment

The development service is named `frigate-dev`. It has its own `/config`, model
cache, database, JWT secret, media directory, and cache tmpfs. Never mount the
production config or media directories into the development container.

Use dedicated host ports, for example `8972:8971`, `8556:8554`, and TCP/UDP
`8557:8555`. Publish `5001:5000` for direct, unauthenticated access to the dev UI
on the trusted LAN. The main service keeps its existing host port 5000. Disable
MQTT, notifications, recording, snapshots, camera control, and detection initially.
Use a fresh database. Copy only the required ONNX model and label map, never the
production compiled model cache, credentials, or database.

Both services share the physical iGPU and host driver. Container separation
isolates data and ports but does not isolate a GPU driver fault. Start testing
with one read-only camera restream and bounded inference. Keep exhaustive tuning
off for routine dev startup. GPU testing must be identified separately from
successful startup with detection disabled.

Before replacing an existing dev container, save its actual configuration and
record its full container and image IDs. Capture and track resources with the
`codex-harness` deployment cleanup helper. After the replacement passes version,
health, data, and application checks, remove only recorded superseded dev
containers and images that have no container references. Running, stopped, and
Created containers all protect their images. Preserve production resources,
appdata, models, keys, media, volumes, and backups. Never use global prune, force
image removal, or volume deletion.

The deployment receipt must include the image digest, full dev container ID,
application version, health and HTTP results, checks that production IDs and
configuration remained unchanged, GPU qualification status, and actual cleanup
results.
