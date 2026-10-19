"""Run bounded inference without cameras, recording, or a Frigate service restart."""

import argparse
import hashlib
import json
import os
import statistics
import time
from pathlib import Path

import cv2
import numpy as np

from frigate.detectors.detector_config import ModelConfig
from frigate.detectors.plugins.migraphx import (
    migraphxDetector,
    migraphxDetectorConfig,
)


def main() -> None:
    """Compile the supplied model and report a small, fixed inference sample."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, type=Path)
    parser.add_argument("--labelmap", required=True, type=Path)
    parser.add_argument("--image", type=Path)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--size", type=int, default=320)
    parser.add_argument("--iterations", type=int, default=5, choices=range(1, 21))
    args = parser.parse_args()

    if args.image:
        image = cv2.imread(str(args.image))
        if image is None:
            raise ValueError("Could not read the qualification image")
        image = cv2.resize(image, (args.size, args.size))
    else:
        image = np.zeros((args.size, args.size, 3), dtype=np.uint8)

    tensor = np.transpose(image.astype(np.float32) / 255, (2, 0, 1))[None, ...]
    config = migraphxDetectorConfig(
        type="migraphx",
        device="gpu",
        conserve_cpu=True,
        fast_math=True,
        exhaustive_tune=False,
        model=ModelConfig(
            path=str(args.model),
            labelmap_path=str(args.labelmap),
            width=args.size,
            height=args.size,
            model_type="yolo-generic",
            input_tensor="nchw",
            input_dtype="float",
            input_pixel_format="bgr",
        ),
    )

    start = time.perf_counter()
    detector = migraphxDetector(config)
    compile_seconds = time.perf_counter() - start
    detector.detect_raw(tensor)
    timings = []
    for _ in range(args.iterations):
        start = time.perf_counter()
        detections = detector.detect_raw(tensor)
        timings.append((time.perf_counter() - start) * 1000)
        if detections.shape != (20, 6) or not np.isfinite(detections).all():
            raise ValueError("Invalid detector output during GPU qualification")

    raw_output_summary = None
    if args.raw_output:
        outputs = detector.model.run(
            {detector.model_param_name: detector.model_input_arg}
        )
        raw_output = np.frombuffer(outputs[0], dtype=np.float32).reshape(
            outputs[0].get_shape().lens()
        )
        if not np.isfinite(raw_output).all():
            raise ValueError("Non-finite network output during GPU qualification")
        np.save(args.raw_output, raw_output)
        raw_output_summary = {
            "shape": list(raw_output.shape),
            "sha256": hashlib.sha256(raw_output.tobytes()).hexdigest(),
        }

    print(
        json.dumps(
            {
                "model_sha256": hashlib.sha256(args.model.read_bytes()).hexdigest(),
                "input_sha256": hashlib.sha256(tensor.tobytes()).hexdigest(),
                "input_shape": list(tensor.shape),
                "pixel_format": "bgr",
                "native_gfx90c": os.environ.get("FRIGATE_ROCM_NATIVE_GFX90C") == "1",
                "hsa_override": os.environ.get("HSA_OVERRIDE_GFX_VERSION"),
                "compile_or_load_seconds": compile_seconds,
                "inference_ms": timings,
                "median_inference_ms": statistics.median(timings),
                "raw_output": raw_output_summary,
                "detections": detections[detections[:, 1] > 0].tolist(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
