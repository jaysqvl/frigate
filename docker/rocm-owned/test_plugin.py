"""Characterize the legacy detector interface on upstream using fake GPU objects."""

import atexit
import importlib.abc
import os
import pkgutil
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

SOURCE_ROOT = Path(
    os.environ.get("FRIGATE_TEST_SOURCE_ROOT", Path(__file__).resolve().parents[2])
)
_workspace = tempfile.TemporaryDirectory(prefix="frigate-migraphx-tests-")
atexit.register(_workspace.cleanup)
WORKTREE = Path(_workspace.name)
shutil.copytree(
    SOURCE_ROOT / "frigate",
    WORKTREE / "frigate",
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
)
sys.path.insert(0, str(WORKTREE))

# Optional runtimes are absent on this CPU-only Mac. Never load vendor bindings.
for name in [
    "py3nvml",
    "py3nvml.py3nvml",
    "tflite_runtime",
    "tflite_runtime.interpreter",
]:
    sys.modules[name] = types.ModuleType(name)
sys.modules["tflite_runtime.interpreter"].Interpreter = MagicMock
sys.modules["tflite_runtime.interpreter"].load_delegate = MagicMock()


class BlockVendorImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {
            "migraphx",
            "onnxruntime",
            "onnxruntime_ep_migraphx",
            "hip",
            "torch",
        }:
            raise AssertionError(f"Vendor runtime import blocked: {fullname}")
        return None


sys.meta_path.insert(0, BlockVendorImports())
_iter_modules = pkgutil.iter_modules


def selected_plugins(path=None, prefix=""):
    modules = list(_iter_modules(path, prefix))
    if prefix == "frigate.detectors.plugins.":
        return iter(
            [
                item
                for item in modules
                if item.name.rsplit(".", 1)[1] in {"cpu_tfl", "migraphx"}
            ]
        )
    return iter(modules)


with patch.object(pkgutil, "iter_modules", selected_plugins):
    from frigate.detectors import create_detector, legacy_amd
    from frigate.detectors.detector_config import ModelConfig
    from frigate.detectors.detector_types import api_types, config_types
    from frigate.detectors.device import build_detector_config, parse_device
    from frigate.detectors.plugins import migraphx as plugin
    from frigate.util.config import migrate_models


class FakeShape:
    def __init__(self, dimensions):
        self.dimensions = dimensions

    def lens(self):
        return self.dimensions


class FakeArgument(np.ndarray):
    def get_shape(self):
        return FakeShape(list(self.shape))


class TestLegacySourceCompatibility(unittest.TestCase):
    def test_sdma_is_set_before_hsa_discovery(self):
        def discover():
            self.assertEqual(os.environ.get("HSA_ENABLE_SDMA"), "0")
            return "gfx90c"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(legacy_amd, "detect_amd_gfx_id", side_effect=discover),
        ):
            legacy_amd.apply_amd_compatibility_env_vars()

    def test_offline_mode_never_probes_hsa(self):
        with (
            patch.dict(os.environ, {"FRIGATE_OFFLINE_CHECK": "1"}),
            patch.object(
                legacy_amd.subprocess,
                "getoutput",
                side_effect=AssertionError("HSA probe blocked"),
            ),
        ):
            self.assertEqual(legacy_amd.detect_amd_gfx_id(), "")

    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for option in ("CONSERVE_CPU", "FAST_MATH", "EXHAUSTIVE_TUNE"):
            os.environ.pop(f"FRIGATE_MIGRAPHX_{option}", None)
        os.environ.pop("FRIGATE_MIGRAPHX_CACHE_NAMESPACE", None)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.labels = self.root / "labels.txt"
        self.labels.write_text("0 person\n58 pottedplant\n")
        self.model = ModelConfig(
            path=str(self.root / "yolo26s-distill_320.onnx"),
            labelmap_path=str(self.labels),
            width=320,
            height=320,
            input_pixel_format="bgr",
            input_tensor="nchw",
            input_dtype="float",
            model_type="yolo-generic",
        )
        Path(self.model.path).write_bytes(b"fake ONNX model for cache tests")

    def config(self):
        return build_detector_config(parse_device("migraphx:GPU"), self.model)

    def test_dynamic_plugin_registry_accepts_restored_detector(self):
        self.assertIs(api_types["migraphx"], plugin.migraphxDetector)
        self.assertIs(config_types["migraphx"], plugin.migraphxDetectorConfig)
        self.assertTrue(parse_device("migraphx:GPU").shareable)
        self.assertIsNone(plugin.migraphxDetector.runtime_manifest)

    def test_new_model_device_builder_preserves_input_contract(self):
        config = self.config()
        self.assertEqual(config.device, "GPU")
        self.assertEqual(config.model.input_tensor, "nchw")
        self.assertEqual(config.model.input_pixel_format, "bgr")
        self.assertEqual(config.model.input_dtype, "float")
        self.assertEqual((config.model.width, config.model.height), (320, 320))

    def test_upstream_migration_loses_legacy_tuning_options(self):
        migrated = migrate_models(
            {
                "detectors": {
                    "rocm": {
                        "type": "migraphx",
                        "device": "GPU",
                        "conserve_cpu": True,
                        "fast_math": True,
                        "exhaustive_tune": True,
                    }
                },
                "model": self.model.model_dump(),
            }
        )
        self.assertEqual(migrated["models"][0]["devices"], ["migraphx:GPU"])
        rebuilt = build_detector_config(
            parse_device("migraphx:GPU"), ModelConfig(**migrated["models"][0])
        )
        self.assertTrue(rebuilt.fast_math)
        self.assertTrue(rebuilt.conserve_cpu)
        self.assertFalse(rebuilt.exhaustive_tune)
        self.assertNotIn("exhaustive_tune", migrated["models"][0])

    def test_amd_compatibility_flags_without_a_hardware_probe(self):
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(legacy_amd, "detect_amd_gfx_id", return_value="gfx90c"),
        ):
            legacy_amd.apply_amd_compatibility_env_vars()
            self.assertEqual(os.environ["HSA_ENABLE_SDMA"], "0")
            self.assertEqual(os.environ["HSA_OVERRIDE_GFX_VERSION"], "9.0.0")
            self.assertEqual(os.environ["MIGRAPHX_DISABLE_MIOPEN_FUSION"], "1")

    def test_explicit_profile_settings_survive_new_device_builder(self):
        with patch.dict(
            os.environ,
            {
                "FRIGATE_MIGRAPHX_CONSERVE_CPU": "1",
                "FRIGATE_MIGRAPHX_FAST_MATH": "1",
                "FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE": "1",
            },
        ):
            config = self.config()
            self.assertTrue(config.conserve_cpu)
            self.assertTrue(config.fast_math)
            self.assertTrue(config.exhaustive_tune)

    def test_native_gfx90c_keeps_sdma_disabled_without_spoofing(self):
        with (
            patch.dict(os.environ, {"FRIGATE_ROCM_NATIVE_GFX90C": "1"}, clear=True),
            patch.object(legacy_amd, "detect_amd_gfx_id", return_value="gfx90c"),
        ):
            legacy_amd.apply_amd_compatibility_env_vars()
            self.assertEqual(os.environ["HSA_ENABLE_SDMA"], "0")
            self.assertNotIn("HSA_OVERRIDE_GFX_VERSION", os.environ)
            self.assertEqual(os.environ["MIGRAPHX_DISABLE_MIOPEN_FUSION"], "1")

    def test_native_profile_preserves_an_explicit_architecture_override(self):
        with (
            patch.dict(
                os.environ,
                {
                    "FRIGATE_ROCM_NATIVE_GFX90C": "1",
                    "HSA_OVERRIDE_GFX_VERSION": "9.0.0",
                },
                clear=True,
            ),
            patch.object(legacy_amd, "detect_amd_gfx_id", return_value="gfx90c"),
        ):
            legacy_amd.apply_amd_compatibility_env_vars()
            self.assertEqual(os.environ["HSA_OVERRIDE_GFX_VERSION"], "9.0.0")

    def test_invalid_profile_setting_is_rejected_before_initialization(self):
        with patch.dict(os.environ, {"FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE": "maybe"}):
            with self.assertRaisesRegex(ValueError, "must be 0 or 1"):
                self.config()

    def construct(self, fast_math=True, exhaustive_tune=True):
        output = np.zeros((1, 300, 6), dtype=np.float32).view(FakeArgument)
        output[0, 0] = [32, 64, 160, 256, 0.9, 0]
        program = MagicMock()
        program.get_output_shapes.return_value = [FakeShape([1, 300, 6])]
        program.get_parameter_names.return_value = ["images"]
        program.get_parameter_shapes.return_value = {
            "images": FakeShape([1, 3, 320, 320])
        }
        program.run.return_value = [output]
        fake = MagicMock()
        fake.parse_onnx.return_value = program
        fake.load.return_value = program
        fake.save.side_effect = lambda model, destination: Path(destination).touch()
        fake.generate_argument.return_value = np.zeros(
            (1, 3, 320, 320), dtype=np.float32
        )
        fake.get_target.return_value = "fake-gpu-target"
        config = self.config()
        config.fast_math = fast_math
        config.exhaustive_tune = exhaustive_tune
        with (
            patch.dict(sys.modules, {"migraphx": fake}),
            patch.object(plugin, "apply_amd_compatibility_env_vars"),
            patch.object(plugin.ctypes, "CDLL") as cdll,
            patch.object(plugin, "MODEL_CACHE_DIR", str(self.root)),
        ):
            detector = create_detector(config)
            cdll.return_value.hipSetDeviceFlags.assert_called_once_with(4)
        return detector, fake, program

    def test_actual_factory_compiles_with_preserved_options_on_fake_gpu(self):
        detector, fake, program = self.construct()
        program.compile.assert_called_once_with(
            "fake-gpu-target", offload_copy=True, fast_math=True, exhaustive_tune=True
        )
        fake.save.assert_called_once()
        self.assertTrue(detector.model_is_e2e)

    def test_actual_factory_reloads_cache_without_recompiling_on_fake_gpu(self):
        self.construct()
        _, fake, program = self.construct()
        fake.load.assert_called_once()
        program.compile.assert_not_called()
        fake.parse_onnx.assert_not_called()

    def test_runtime_namespace_ignores_other_runtime_and_adjacent_caches(self):
        self.construct()
        (self.root / "yolo26s-distill_320_tune.mxr").touch()
        with patch.dict(os.environ, {"FRIGATE_MIGRAPHX_CACHE_NAMESPACE": "owned101"}):
            _, fake, program = self.construct()
        fake.load.assert_not_called()
        program.compile.assert_called_once()
        destination = Path(fake.save.call_args.args[1])
        self.assertEqual(destination.parent, self.root / "migraphx/owned101")

    def test_replacing_model_contents_does_not_reuse_compiled_cache(self):
        _, original, _ = self.construct()
        Path(self.model.path).write_bytes(b"replacement ONNX model")
        _, updated, program = self.construct()
        updated.load.assert_not_called()
        program.compile.assert_called_once()
        self.assertNotEqual(
            original.save.call_args.args[1], updated.save.call_args.args[1]
        )

    def test_changing_compiler_options_does_not_reuse_compiled_cache(self):
        self.construct()
        for options in (
            {"fast_math": False},
            {"exhaustive_tune": False},
        ):
            with self.subTest(options=options):
                _, fake, program = self.construct(**options)
                fake.load.assert_not_called()
                program.compile.assert_called_once()

    def test_changing_architecture_override_does_not_reuse_compiled_cache(self):
        self.construct()
        with patch.dict(os.environ, {"HSA_OVERRIDE_GFX_VERSION": "9.0.0"}):
            _, fake, program = self.construct()
        fake.load.assert_not_called()
        program.compile.assert_called_once()

    def test_cache_namespace_cannot_escape_its_directory(self):
        with patch.dict(os.environ, {"FRIGATE_MIGRAPHX_CACHE_NAMESPACE": "../other"}):
            with self.assertRaisesRegex(ValueError, "cache namespace"):
                self.construct()

    def test_detect_raw_preserves_nchw_values_and_e2e_box_order(self):
        detector, _, program = self.construct()
        tensor = np.zeros((1, 3, 320, 320), dtype=np.float32)
        tensor[:, 0] = 0.2
        tensor[:, 1] = 0.4
        tensor[:, 2] = 0.8
        actual = detector.detect_raw(tensor)
        self.assertTrue(np.array_equal(detector.model_input_array, tensor))
        self.assertTrue(np.allclose(actual[0], [0, 0.9, 0.2, 0.1, 0.8, 0.5], atol=1e-7))
        self.assertEqual(actual.shape, (20, 6))
        self.assertEqual(actual.dtype, np.float32)
        self.assertTrue((actual[1:] == 0).all())
        program.run.assert_called_once()

    def test_e2e_parser_retains_overlaps_and_limits_sorted_detections(self):
        detector, _, _ = self.construct()
        output = np.zeros((1, 300, 6), dtype=np.float32)
        output[0, :25] = [32, 64, 160, 256, 0.9, 0]
        output[0, 0, 4] = 0.95
        output[0, 25] = [32, 64, 160, 256, 0.4, 0]
        actual = detector._process_yolo_e2e(output, 0.4)
        self.assertEqual(np.count_nonzero(actual[:, 1]), 20)
        self.assertAlmostEqual(float(actual[0, 1]), 0.95, places=6)


if __name__ == "__main__":
    tests = [f"{__name__}.TestLegacySourceCompatibility"]
    if "--with-config-tests" in sys.argv:
        sys.argv.remove("--with-config-tests")
        # Keep the omitted optional plugin's exclusivity contract for migrations.
        config_types["edgetpu"] = types.SimpleNamespace(shareable=False)
        tests.append("frigate.test.test_config_migration")
    # No subprocess, network, or native-library calls are allowed by the probe.
    with (
        patch("subprocess.Popen", side_effect=AssertionError("Subprocess blocked")),
        patch("ctypes.CDLL", side_effect=AssertionError("Native library blocked")),
        patch("socket.socket.connect", side_effect=AssertionError("Network blocked")),
    ):
        suite = unittest.defaultTestLoader.loadTestsFromNames(tests)
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
