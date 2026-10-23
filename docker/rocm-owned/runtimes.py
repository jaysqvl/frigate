"""Pin released AMD runtimes and generate Docker Bake inputs for this checkout."""

import argparse
import hashlib
import json
import re
import subprocess
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LOCK = HERE / "runtime-lock.json"
PROFILES = ("rocm-7.2.4", "rocm-10.1-gfx90c", "rocm-10.1-vega", "rocm-10.1")
RUNTIME_REPO = "jaysqvl/AMDMIGraphX"


def hexadecimal(value: str, length: int) -> bool:
    """Require a complete immutable identity, not a placeholder."""
    return bool(re.fullmatch(rf"[0-9a-f]{{{length}}}", value)) and set(value) != {"0"}


def validate_profile(name: str, entry: dict) -> None:
    """Check the runtime/application ABI and the recorded publication evidence."""
    assert name in PROFILES
    expected_rocm = "7.2.4" if name == "rocm-7.2.4" else "10.1.0"
    assert entry["configuration"]["rocm"] == expected_rocm
    assert entry["configuration"]["python_abi"] == "cp311"
    assert entry["configuration"]["status"] == "experimental"
    assert hexadecimal(entry["source_commit"], 40)
    assert hexadecimal(entry["runtime_recipe_sha256"], 64)
    assert hexadecimal(entry["metadata_sha256"], 64)
    prefix = "ghcr.io/jaysqvl/frigate-runtime-" + name + "@sha256:"
    assert entry["image"].startswith(prefix)
    assert hexadecimal(entry["image"].removeprefix(prefix), 64)
    targets = entry["configuration"]["gpu_targets"]
    assert targets and len(targets) == len(set(targets))
    assert all(re.fullmatch(r"gfx[0-9a-f]+", target) for target in targets)


def load_lock(path: Path = LOCK) -> dict:
    """Reject partial releases or accidentally mixing different runtime sources."""
    lock = json.loads(path.read_text())
    assert lock["schema"] == 1 and lock["repository"] == RUNTIME_REPO
    assert re.fullmatch(r"runtime-v[0-9][A-Za-z0-9._-]*", lock["release"])
    assert set(lock["profiles"]) == set(PROFILES)
    for name, entry in lock["profiles"].items():
        validate_profile(name, entry)
    assert len({entry["source_commit"] for entry in lock["profiles"].values()}) == 1
    return lock


def update_lock(release: str, path: Path = LOCK) -> dict:
    """Import all four public release manifests; never follow a mutable image tag."""
    if not re.fullmatch(r"runtime-v[0-9][A-Za-z0-9._-]*", release):
        raise ValueError("Use a runtime-vVERSION release tag")
    lock = {"schema": 1, "repository": RUNTIME_REPO, "release": release, "profiles": {}}
    for name in PROFILES:
        url = (
            f"https://github.com/{RUNTIME_REPO}/releases/download/{release}/{name}.json"
        )
        with urllib.request.urlopen(url, timeout=120) as response:
            raw = response.read(1024 * 1024 + 1)
        assert len(raw) <= 1024 * 1024
        metadata = json.loads(raw)
        assert metadata["profile"] == name
        assert metadata["source_repository"] == "https://github.com/" + RUNTIME_REPO
        assert metadata["gpu_tested"] is False
        checks = metadata["verification"]
        assert (
            checks["native_files_checked"] > 0
            and checks["unresolved_dependencies"] == 0
        )
        assert checks["python_import"] == "passed"
        assert (
            checks["reference_arithmetic"] == "passed"
            and checks["onednn_cpu_arithmetic"] == "passed"
        )
        assert checks["gpu_devices_exposed"] is False and checks["gpu_tested"] is False
        actual = {(obj["arch"], obj["dtype"]) for obj in checks["offline_mlir_objects"]}
        expected = {
            (arch, dtype)
            for arch in metadata["configuration"]["gpu_targets"]
            for dtype in ("fp32", "fp16")
        }
        assert actual == expected
        required_data = {"rocblas": metadata["configuration"]["gpu_targets"]}
        if metadata["configuration"]["hipblaslt_targets"]:
            required_data["hipblaslt"] = metadata["configuration"]["hipblaslt_targets"]
        kernel_data = checks["blas_kernel_data"]
        assert set(kernel_data) == set(required_data)
        for component, targets in required_data.items():
            assert set(kernel_data[component]) == set(targets)
            assert all(
                row["metadata_files"] > 0 and row["code_objects"] > 0
                for row in kernel_data[component].values()
            )
        entry = {
            key: metadata[key]
            for key in (
                "image",
                "source_commit",
                "runtime_recipe_sha256",
                "configuration",
            )
        }
        entry["metadata_sha256"] = hashlib.sha256(raw).hexdigest()
        validate_profile(name, entry)
        lock["profiles"][name] = entry
    assert len({entry["source_commit"] for entry in lock["profiles"].values()}) == 1
    path.write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def bake(
    lock: dict, profile: str, base_image: str | None = None, tag: str | None = None
) -> dict:
    """Build the checked-out Frigate source with one independently pinned runtime."""
    entry = lock["profiles"][profile]
    validate_profile(profile, entry)
    adapter = hashlib.sha256()
    adapter.update(entry["image"].encode())
    for name in ("legacy_amd.py", "plugins/migraphx.py"):
        adapter.update((ROOT / "frigate/detectors" / name).read_bytes())
    settings = {
        "target": "rocm-general"
        if profile == "rocm-10.1"
        else ("rocm-legacy" if profile == "rocm-7.2.4" else "rocm-native"),
        "contexts": {"amd-runtime": "docker-image://" + entry["image"]},
        "args": {
            "RUNTIME_DIRECTORY": "rocm-" + entry["configuration"]["rocm"],
            "RUNTIME_PROFILE": profile,
            "RUNTIME_IMAGE": entry["image"],
            "CACHE_NAMESPACE": profile + "-" + adapter.hexdigest()[:16],
            "SOURCE_COMMIT": subprocess.run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip(),
        },
    }
    if base_image:
        assert re.fullmatch(r"ghcr.io/jaysqvl/frigate@sha256:[0-9a-f]{64}", base_image)
        settings["contexts"]["frigate-base"] = "docker-image://" + base_image
    if tag:
        assert re.fullmatch(r"[a-z0-9./-]+:[A-Za-z0-9._-]+", tag)
        settings["tags"] = [tag]
    return {"target": {"frigate-rocm": settings}}


def main():
    """Keep updating the runtime lock separate from ordinary Frigate builds."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("update", "check", "bake"))
    parser.add_argument("--release")
    parser.add_argument("--lock", type=Path, default=LOCK)
    parser.add_argument("--profile", choices=PROFILES)
    parser.add_argument("--base-image")
    parser.add_argument("--tag")
    args = parser.parse_args()
    if args.mode == "update":
        if not args.release:
            parser.error("update requires --release")
        lock = update_lock(args.release, args.lock)
    else:
        lock = load_lock(args.lock)
    if args.mode == "bake":
        if not args.profile:
            parser.error("bake requires --profile")
        print(json.dumps(bake(lock, args.profile, args.base_image, args.tag), indent=2))
    else:
        print(
            json.dumps(
                {"release": lock["release"], "profiles": list(lock["profiles"])},
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
