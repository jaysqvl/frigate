# The standard upstream image supplies the current application, frontend, and OS.
# Only the frozen ROCm runtime is taken from the working legacy image.
ARG FRIGATE_IMAGE=ghcr.io/blakeblackshear/frigate@sha256:d9004df234df7e6ec701d37be4db60610e2c604614cb831bb369067388a6b460
ARG LEGACY_RUNTIME_IMAGE=ghcr.io/garymathews/frigate@sha256:4d16caffb39a3d34976828c1a558bca6a9c9067dc7fbd577f9109ba4f7dcefab

FROM ${LEGACY_RUNTIME_IMAGE} AS legacy-runtime

FROM ${FRIGATE_IMAGE} AS frigate-legacy724
USER root

COPY --from=legacy-runtime /opt/rocm-7.2.4/ /opt/rocm-7.2.4/
# Keep the same C++ headers and GCC support files used by HIPRTC fallback.
COPY --from=legacy-runtime /usr/include/c++/14/ /usr/include/c++/14/
COPY --from=legacy-runtime /usr/include/x86_64-linux-gnu/c++/14/ /usr/include/x86_64-linux-gnu/c++/14/
COPY --from=legacy-runtime /usr/lib/gcc/x86_64-linux-gnu/14/ /usr/lib/gcc/x86_64-linux-gnu/14/
# These two OS libraries are absent from the standard image. Keep the exact
# versions used by the frozen runtime rather than resolving new apt packages.
COPY --from=legacy-runtime /usr/lib/x86_64-linux-gnu/libnuma.so.* /usr/lib/x86_64-linux-gnu/
COPY --from=legacy-runtime /usr/lib/llvm-19/lib/libomp.so* /usr/lib/x86_64-linux-gnu/

ENV HSA_ENABLE_SDMA=0 \
    HSA_OVERRIDE_GFX_VERSION=9.0.0 \
    MIGRAPHX_DISABLE_MIOPEN_FUSION=1 \
    MIGRAPHX_DISABLE_SCHEDULE_PASS=1 \
    MIGRAPHX_DISABLE_REDUCE_FUSION=1 \
    MIGRAPHX_ENABLE_HIPRTC_WORKAROUNDS=1 \
    MIOPEN_CUSTOM_CACHE_DIR=/config/model_cache/migraphx \
    MIOPEN_USER_DB_PATH=/config/model_cache/migraphx \
    AMD_COMGR_CACHE=1 \
    AMD_COMGR_CACHE_DIR=/config/model_cache/migraphx \
    FRIGATE_MIGRAPHX_CONSERVE_CPU=1 \
    FRIGATE_MIGRAPHX_FAST_MATH=1 \
    FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE=1

RUN test ! -e /opt/rocm \
    && ln -s rocm-7.2.4 /opt/rocm \
    && printf '/opt/rocm/lib\n/opt/rocm/lib/migraphx/lib\n' > /etc/ld.so.conf.d/rocm-legacy724.conf \
    && ldconfig

WORKDIR /opt/frigate
COPY frigate/detectors/plugins/migraphx.py frigate/detectors/plugins/migraphx.py
COPY frigate/detectors/legacy_amd.py frigate/detectors/legacy_amd.py

RUN python3 -m compileall -q frigate/detectors/plugins/migraphx.py frigate/detectors/legacy_amd.py

LABEL org.opencontainers.image.source="https://github.com/jaysqvl/frigate" \
    io.jaysqvl.frigate.upstream="5bb2cde8b39b682e5b583f224bd58cc9ea975608" \
    io.jaysqvl.frigate.runtime="rocm-7.2.4-migraphx-2.15.0-gfx900" \
    io.jaysqvl.frigate.qualification="offline-no-gpu"
