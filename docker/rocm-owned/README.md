# Frigate with independently built AMD runtimes

This integration keeps AMD builds outside Frigate. The
[runtime repository](https://github.com/jaysqvl/AMDMIGraphX/tree/main/packaging/frigate)
owns the source locks, SDK packaging, compiler builds, GPU target profiles, and
runtime releases. Frigate consumes an immutable runtime image digest.

The application delta is the restored direct MIGraphX detector, its AMD
compatibility helper, and this image integration. Normal upstream merges do not
require copying or rebasing LLVM, rocMLIR, Tensile, or AMD build recipes here.
The shared Frigate adapter works with both runtime versions and does not need a
custom ONNX Runtime wheel.
GPU acceleration here covers the direct MIGraphX object detector. Features that
use ONNX Runtime separately retain upstream's CPU provider in these images.

## Profiles and status

`runtime-lock.json` pins all four profiles from one runtime release:

| Image suffix | Intended build profile |
| --- | --- |
| `rocm-10.1` | RDNA 3/4 targets, standard AMD SDK BLAS |
| `rocm-10.1-vega` | Source-built rocBLAS for gfx900, gfx906 and gfx90c |
| `rocm-10.1-gfx90c` | Focused native gfx90c compatibility build |
| `rocm-7.2.4` | Gary's broad target list with legacy gfx900 kernel data |

These profiles are **experimental**, not a claim that every corresponding GPU
has been tested. CI checks compiling/linking and application migration without
GPU access. Earlier 5700G comparisons used different artifacts. New public
binaries need their own hardware checks before production migration.

After a successful current-main image workflow, the update channels are
`ghcr.io/jaysqvl/frigate:latest-<profile>`. For example, a Ryzen 7 5700G uses:

```sh
docker pull ghcr.io/jaysqvl/frigate:latest-rocm-10.1-gfx90c
```

Use that tag as the Unraid **Repository** or Compose `image` to see and pull
future updates. Pulling or publishing an image does not change a running
container; choose Update/Recreate in your deployment manager to apply it.
The existing `experimental-<profile>` tags remain aliases of the same images.

Every successful current-main build also creates a development
[GitHub Release](https://github.com/jaysqvl/frigate/releases) with versioned
image tags and four manifests. The default release tag is
`frigate-v<Frigate version>-dev.<workflow run number>.<attempt>`.
Use the versioned image or manifest digest to keep a deployment fixed while
the update channels advance. These development releases are not upstream
Frigate stable releases.

The image sets `HSA_ENABLE_SDMA=0` before HSA discovery. Legacy profiles retain
the measured MIGraphX workarounds; the modern profile omits them. The 7.2.4
compatibility helper detects legacy APUs and applies their gfx900 override.
Native 10.1 gfx90c retains SDMA disabled without forcing a gfx900 identity.
An explicitly configured environment value takes precedence.

Existing `migraphx` detector configs migrate to `migraphx:GPU` model devices.
For a new config, select `migraphx:GPU` in the model's `devices` list, and keep
the model's dimensions, pixel format, dtype, and label map consistent. YOLO
end-to-end `[1, N, 6]` output remains supported. Runtime and adapter identities
separate compiled model caches across image profiles.
Model contents, compiler options, and explicit device overrides also participate
in cache keys. Old adjacent `.mxr` files are not imported automatically.

Upstream's model-device config does not carry the former per-detector tuning
fields. These images default conserve-CPU, fast math, and exhaustive tuning to
enabled. Set `FRIGATE_MIGRAPHX_CONSERVE_CPU`, `FRIGATE_MIGRAPHX_FAST_MATH`, or
`FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE` to `0` or `1` to override those defaults.

## Build and release

For normal use, run one of these from GitHub's **Actions** tab on `main`:

- [Sync upstream and build](https://github.com/jaysqvl/frigate/actions/workflows/sync-upstream.yml):
  click **Run workflow** to sync upstream `dev`, test the proposed merge with
  Frigate's existing backend/frontend checks, update this fork's `main`, and
  dispatch **Owned ROCm images**. Merge conflicts or failed checks leave `main`
  unchanged. The temporary sync branch is removed after the run.
- [Owned ROCm images](https://github.com/jaysqvl/frigate/actions/workflows/owned-rocm.yml):
  click **Run workflow** to rebuild the current Frigate source with all four
  pinned runtimes. Leave `release_tag` empty to generate the release name
  automatically, or supply a new unused `frigate-vVERSION` tag.

Both entry points use GitHub-hosted Linux runners and need no NAS access or
additional secrets. Follow **Owned ROCm images** for the final build result.
Its `latest-<profile>` and `experimental-<profile>` tags advance only after
every profile passes and the source release is published, with the source still
at the current `main` commit. Deployment is a separate step; these workflows
leave running Frigate instances alone.

The same buttons are available through GitHub CLI from any directory:

```sh
gh workflow run sync-upstream.yml --repo jaysqvl/frigate --ref main
# Or rebuild without syncing upstream:
gh workflow run owned-rocm.yml --repo jaysqvl/frigate --ref main
```

Rebuilding AMD itself is less frequent. Open
[Frigate AMD runtimes](https://github.com/jaysqvl/AMDMIGraphX/actions/workflows/frigate-runtime.yml),
select `main`, and run it with a new unused `release_tag`, such as
`runtime-v0.1.6`. It builds and checks all four profiles, publishes their OCI
images and archives, and completes the runtime prerelease after all pass.
The source locks stay explicit: syncing an AMD mirror does not upgrade a pinned
runtime. After reviewing a new runtime release, import it with the update command
below and commit the lock. Normal Frigate updates reuse the existing runtime.

For a local build instead, use the repository root with a Linux amd64 Docker builder:

```sh
make version
mkdir -p tmp/owned-rocm
python3 docker/rocm-owned/runtimes.py bake --profile rocm-10.1-gfx90c \
  --tag frigate:owned-test > tmp/owned-rocm/bake.json
docker buildx bake -f docker/rocm-owned/docker-bake.hcl \
  -f tmp/owned-rocm/bake.json frigate-rocm --load
bash docker/rocm-owned/check-image.sh frigate:owned-test tmp/owned-rocm/checks
```

Docker Bake builds the checked-out Frigate source, web UI, and dependencies with
upstream's Dockerfile, then adds the selected runtime. It does not overlay a
couple of source files onto an older prebuilt application image.

The **Owned ROCm images** workflow runs pin/selection, adapter, cache, and config
migration checks on PRs. On `main`
pushes or manual dispatch, it builds the application once and layers all four
runtimes on that exact base digest. Images publish only after native linking,
explicit-target HIPRTC helper compilation, detector tests, and config/database
migration checks pass. After every profile passes, the workflow publishes a
development GitHub Release and four versioned images, then advances the moving
update channels for the current `main` commit. A `frigate-vVERSION` tag or manual
`release_tag` overrides the generated release name.
Each manifest records the shared application base digest, selected runtime,
final image digest, source commit, and offline check-log hashes.
Neither workflow deploys an instance, starts cameras, or uses production data.

Each final image also boots Frigate in a temporary CI container with no external
network or GPU devices, an empty camera configuration, recording and auth off,
and volatile appdata. Its API must report the expected source version, Docker's
health check must pass, and its fresh database must pass an integrity check.
The container is stopped and removed by its recorded ID; no ports are published.

Database checks seed a synthetic database at Gary's migration 035 boundary,
apply the latest migrations twice, and verify preserved rows and integrity.
This complements the upstream config migration tests; it is not a replacement
for a backed-up production appdata upgrade test before a real cutover.

To adopt a newly verified runtime release:

```sh
python3 docker/rocm-owned/runtimes.py update --release runtime-vVERSION
python3 docker/rocm-owned/runtimes.py check
```

Review the runtime lock diff, commit it, and let the application workflow run.
The importer requires all four profiles, their complete compiler checks, a
consistent source revision, CPython 3.11, and immutable OCI digests.

## Upstream sync

`dev` is the upstream development mirror; `main` carries the small shared
integration. Sync upstream `dev`, then merge it into this fork's `main` through a
PR targeting **jaysqvl/frigate**. Review detector/config interface changes and
the offline image checks. AMD runtimes remain pinned until deliberately updated.
An upstream Python ABI or base-library change may require rebuilding the binding;
the image build checks the CPython ABI before accepting the runtime.
The older comparison branches retain the earlier qualification snapshots.

The **Sync upstream and build** workflow is the normal update entry point. It
uses GitHub's fork-sync and merge APIs and the existing reusable PR checks. A
non-forced main update rejects a concurrent conflicting change.

For a manual PR-based refresh, use the fork explicitly in every GitHub command:

```sh
gh repo sync jaysqvl/frigate --branch dev
git fetch origin
git switch -c sync/upstream-dev origin/main
git merge origin/dev
git push -u origin sync/upstream-dev
gh pr create --repo jaysqvl/frigate --base main --head sync/upstream-dev
```

Use a fresh sync branch name if that branch already exists. Review and merge the
PR after the adapter/config checks pass, then check the built images. The
inherited `ci.yml` and `release.yml` image publishers are disabled in this fork;
syncing `dev` alone does not publish the older image tags. Upstream PR checks
remain enabled.

The AMD source forks use `develop` as their mirror. Sync their `develop`
branches in the same way. Only `jaysqvl/AMDMIGraphX` carries our packaging on
`main`; the unmodified rocMLIR and rocm-libraries mirrors need no integration
branch. The `frigate-pinned-*` tags retain the exact selected AMD source commits
when those mirror branches advance. A mirror sync never changes runtime pins.
