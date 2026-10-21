# Owned ROCm 10.1 legacy runtime

This profile uses the same direct MIGraphX detector contract as the 7.2.4
profile. It builds MIGraphX 2.18, classic rocMLIR API 6, and rocBLAS/Tensile
from immutable source, against AMD's stable 10.1 SDK.

The classic compiler is an intentional compatibility choice. The stock
10.1 ONNX Runtime MIGraphX provider uses a different Triton compiler that
previously crashed on gfx90c. This recipe does not fix or use that provider.

Native gfx90c kernels come from the pinned rocBLAS/Tensile source build.
Tensile recognizes gfx90c and maps it to Vega 10, but the shipped Vega 10
logic names gfx900. retarget_logic.py changes only the architecture header
in the 46 selected asm_full files. Tensile then derives and compiles the
gfx90c ISA; kernel tuning values remain unchanged. This requires hardware
correctness testing before acceptance.
No earlier-release BLAS kernels or nightly SDK device wheel are substituted.
hipBLASLt and Composable Kernel are disabled for this legacy target, following
the referenced community legacy profile. CPU/oneDNN, MIOpen, rocBLAS, MLIR,
ONNX, TensorFlow, and the CPython 3.11 binding remain enabled.

Build and qualification are provided by ../owned/pipeline.py. Compilation
and offline checks have no GPU devices and no network. Acquisition is a
separate, hash-verified step. A passing build is not GPU qualification.
