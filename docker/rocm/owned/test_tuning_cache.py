"""Keep interrupted native tuning within its proven private cache."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from qualify_model import configure_tuning_cache


class TestTuningCache(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.cache = Path("/config/model_cache/migraphx/native-own/model_tune.mxr")

    def test_older_backend_does_not_use_native_cache_format(self):
        self.assertEqual(configure_tuning_cache(self.cache), {})
        self.assertNotIn("MIGRAPHX_GPU_OPTIONS", os.environ)

    def test_native_cache_is_private_and_completed_choices_are_saved(self):
        os.environ["FRIGATE_ROCM_NATIVE_GFX90C"] = "1"
        settings = configure_tuning_cache(self.cache)
        self.assertEqual(
            json.loads(settings["MIGRAPHX_GPU_OPTIONS"]),
            {"problem_cache_files": [str(self.cache.parent / "problems.json")]},
        )
        self.assertEqual(settings["MIGRAPHX_TRACE_BENCHMARKING"], "1")
        self.assertEqual(configure_tuning_cache(self.cache), settings)

    def test_inherited_backend_or_trace_settings_are_rejected(self):
        os.environ["FRIGATE_ROCM_NATIVE_GFX90C"] = "1"
        for key, value in (
            ("MIGRAPHX_GPU_OPTIONS", '{"convolution_layout":"channels_last"}'),
            ("MIGRAPHX_TRACE_BENCHMARKING", "0"),
        ):
            with patch.dict(os.environ, {key: value}):
                with self.subTest(key=key), self.assertRaises(ValueError):
                    configure_tuning_cache(self.cache)


if __name__ == "__main__":
    unittest.main()
