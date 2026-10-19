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

The `rocm-10.1-gfx90c` experiment uses a separate branch and candidate tag. Its
Frigate application should remain at the same baseline while the runtime is
qualified, so inference results can be compared without an application upgrade.

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
