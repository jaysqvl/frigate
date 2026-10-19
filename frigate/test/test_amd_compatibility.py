"""Check that native Vega images cannot silently select spoofed GPU kernels."""

import os
import unittest
from unittest.mock import patch

from frigate.detectors.detector_utils import apply_amd_compatibility_env_vars


class TestAmdCompatibility(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="gfx90c")
    def test_legacy_vega_keeps_gfx900_override(self, _detect):
        apply_amd_compatibility_env_vars()

        self.assertEqual(os.environ["HSA_OVERRIDE_GFX_VERSION"], "9.0.0")
        self.assertEqual(os.environ["HSA_ENABLE_SDMA"], "0")

    @patch.dict(os.environ, {"FRIGATE_ROCM_NATIVE_GFX90C": "1"}, clear=True)
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="gfx90c")
    def test_native_vega_does_not_spoof_gpu_architecture(self, _detect):
        apply_amd_compatibility_env_vars()

        self.assertNotIn("HSA_OVERRIDE_GFX_VERSION", os.environ)
        self.assertEqual(os.environ["HSA_ENABLE_SDMA"], "0")
        self.assertEqual(os.environ["MIGRAPHX_DISABLE_MIOPEN_FUSION"], "1")

    @patch.dict(
        os.environ,
        {"FRIGATE_ROCM_NATIVE_GFX90C": "1", "HSA_OVERRIDE_GFX_VERSION": "9.0.0"},
        clear=True,
    )
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="gfx90c")
    def test_native_vega_rejects_an_inherited_architecture_override(self, _detect):
        with self.assertRaisesRegex(RuntimeError, "must|unset"):
            apply_amd_compatibility_env_vars()

    @patch.dict(os.environ, {"FRIGATE_ROCM_NATIVE_GFX90C": "1"}, clear=True)
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="gfx900")
    def test_native_vega_rejects_a_different_gpu(self, _detect):
        with self.assertRaisesRegex(RuntimeError, "requires a gfx90c GPU"):
            apply_amd_compatibility_env_vars()

    @patch.dict(os.environ, {"FRIGATE_ROCM_NATIVE_GFX90C": "1"}, clear=True)
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="")
    def test_native_vega_requires_successful_gpu_detection(self, _detect):
        with self.assertRaisesRegex(RuntimeError, "Unable to detect"):
            apply_amd_compatibility_env_vars()

    @patch.dict(os.environ, {}, clear=True)
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="")
    def test_legacy_image_without_a_gpu_keeps_its_environment(self, _detect):
        apply_amd_compatibility_env_vars()

        self.assertEqual(dict(os.environ), {})

    @patch.dict(os.environ, {"HSA_ENABLE_SDMA": "1"}, clear=True)
    @patch("frigate.detectors.detector_utils.detect_amd_gfx_id", return_value="gfx90c")
    def test_explicit_workaround_value_is_preserved(self, _detect):
        apply_amd_compatibility_env_vars()

        self.assertEqual(os.environ["HSA_ENABLE_SDMA"], "1")


if __name__ == "__main__":
    unittest.main()
