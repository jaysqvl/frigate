"""Test runtime selection without a Docker daemon or AMD runtime."""

import copy
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtimes


def metadata(name):
    """Construct public release metadata for network-free protocol tests."""
    checksum = hashlib.sha256(name.encode()).hexdigest()
    targets = ["gfx900"] if name == "rocm-7.2.4" else ["gfx90c"]
    hipblaslt_targets = targets if name == "rocm-10.1" else []
    return {
        "profile": name,
        "image": f"ghcr.io/jaysqvl/frigate-runtime-{name}@sha256:{checksum}",
        "source_repository": "https://github.com/jaysqvl/AMDMIGraphX",
        "source_commit": "a" * 40,
        "runtime_recipe_sha256": checksum,
        "gpu_tested": False,
        "configuration": {
            "rocm": "7.2.4" if name == "rocm-7.2.4" else "10.1.0",
            "python_abi": "cp311",
            "status": "experimental",
            "gpu_targets": targets,
            "hipblaslt_targets": hipblaslt_targets,
        },
        "verification": {
            "native_files_checked": 2,
            "unresolved_dependencies": 0,
            "python_import": "passed",
            "reference_arithmetic": "passed",
            "onednn_cpu_arithmetic": "passed",
            "gpu_devices_exposed": False,
            "gpu_tested": False,
            "offline_mlir_objects": [
                {"arch": arch, "dtype": dtype}
                for arch in targets
                for dtype in ("fp32", "fp16")
            ],
            "blas_kernel_data": {
                component: {
                    arch: {"metadata_files": 1, "code_objects": 1}
                    for arch in architectures
                }
                for component, architectures in (
                    {"rocblas": targets, "hipblaslt": hipblaslt_targets}
                    if hipblaslt_targets
                    else {"rocblas": targets}
                ).items()
            },
        },
    }


class RuntimeSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "runtime-lock.json"

    def release(self, change=None):
        def response(url, **kwargs):
            name = url.rsplit("/", 1)[1].removesuffix(".json")
            value = metadata(name)
            if change:
                change(value)
            return io.BytesIO(json.dumps(value).encode())

        with patch.object(runtimes.urllib.request, "urlopen", side_effect=response):
            return runtimes.update_lock("runtime-v1.0.0", self.path)

    def test_imports_complete_release_with_immutable_digests(self):
        self.release()
        lock = runtimes.load_lock(self.path)
        self.assertEqual(set(lock["profiles"]), set(runtimes.PROFILES))

    def test_rejects_missing_compiler_target_and_does_not_write_partial_lock(self):
        def remove(value):
            value["verification"]["offline_mlir_objects"].pop()

        with self.assertRaises(AssertionError):
            self.release(remove)
        self.assertFalse(self.path.exists())

    def test_rejects_wrong_abi_and_unrelated_registry(self):
        for field, value in (("python_abi", "cp313"), ("rocm", "99")):

            def change(metadata_value):
                metadata_value["configuration"][field] = value

            with self.assertRaises(AssertionError):
                self.release(change)
        with self.assertRaises(AssertionError):
            self.release(
                lambda value: value.update(image="ghcr.io/other/runtime:latest")
            )

    def test_rejects_missing_blas_data_and_does_not_write_partial_lock(self):
        def remove(value):
            value["verification"]["blas_kernel_data"]["rocblas"].clear()

        with self.assertRaises(AssertionError):
            self.release(remove)
        self.assertFalse(self.path.exists())

    def test_bake_uses_checked_out_source_and_separate_runtime_context(self):
        lock = self.release()
        result = runtimes.bake(lock, "rocm-10.1-gfx90c")["target"]["frigate-rocm"]
        self.assertNotIn("frigate-base", result["contexts"])
        self.assertIn("@sha256:", result["contexts"]["amd-runtime"])
        self.assertEqual(result["target"], "rocm-native")
        self.assertRegex(result["args"]["SOURCE_COMMIT"], "^[0-9a-f]{40}$")

    def test_runtime_change_invalidates_cache_namespace(self):
        lock = self.release()
        before = runtimes.bake(lock, "rocm-10.1")["target"]["frigate-rocm"]["args"][
            "CACHE_NAMESPACE"
        ]
        changed = copy.deepcopy(lock)
        changed["profiles"]["rocm-10.1"]["image"] = (
            "ghcr.io/jaysqvl/frigate-runtime-rocm-10.1@sha256:" + "b" * 64
        )
        after = runtimes.bake(changed, "rocm-10.1")["target"]["frigate-rocm"]["args"][
            "CACHE_NAMESPACE"
        ]
        self.assertNotEqual(before, after)

    def test_modern_profile_has_no_legacy_workaround_stage(self):
        self.assertEqual(
            runtimes.bake(self.release(), "rocm-10.1")["target"]["frigate-rocm"][
                "target"
            ],
            "rocm-general",
        )

    def test_release_path_traversal_is_rejected_before_network_access(self):
        with patch.object(
            runtimes.urllib.request,
            "urlopen",
            side_effect=AssertionError("network blocked"),
        ):
            with self.assertRaises(ValueError):
                runtimes.update_lock("../bad", self.path)


if __name__ == "__main__":
    unittest.main()
