# syntax=docker/dockerfile:1.6
# Both contexts are supplied by Docker Bake. The base contains this checkout.
FROM frigate-base AS rocm-general
USER root
COPY --from=amd-runtime / /
ARG RUNTIME_DIRECTORY
ARG RUNTIME_PROFILE
ARG RUNTIME_IMAGE
ARG CACHE_NAMESPACE
ARG SOURCE_COMMIT
ENV LD_LIBRARY_PATH=/opt/rocm/lib/migraphx/lib:/opt/rocm/lib:/opt/rocm/lib/llvm/lib:${LD_LIBRARY_PATH} \
    PYTHONPATH=/opt/rocm/lib:${PYTHONPATH} \
    HSA_ENABLE_SDMA=0 \
    FRIGATE_SOURCE_COMMIT=${SOURCE_COMMIT} \
    FRIGATE_ROCM_PROFILE=${RUNTIME_PROFILE} \
    FRIGATE_MIGRAPHX_CACHE_NAMESPACE=${CACHE_NAMESPACE} \
    MIOPEN_CUSTOM_CACHE_DIR=/config/model_cache/migraphx/${CACHE_NAMESPACE} \
    MIOPEN_USER_DB_PATH=/config/model_cache/migraphx/${CACHE_NAMESPACE} \
    AMD_COMGR_CACHE=1 \
    AMD_COMGR_CACHE_DIR=/config/model_cache/migraphx/${CACHE_NAMESPACE} \
    FRIGATE_MIGRAPHX_CONSERVE_CPU=1 \
    FRIGATE_MIGRAPHX_FAST_MATH=1 \
    FRIGATE_MIGRAPHX_EXHAUSTIVE_TUNE=1
RUN --network=none test ! -e /dev/kfd && test ! -e /dev/dri \
    && test ! -e /opt/rocm && ln -s "${RUNTIME_DIRECTORY}" /opt/rocm \
    && printf '/opt/rocm/lib\n/opt/rocm/lib/migraphx/lib\n/opt/rocm/lib/llvm/lib\n' > /etc/ld.so.conf.d/frigate-owned-rocm.conf \
    && ldconfig \
    && python3 -c 'import json, os, sys; assert sys.version_info[:2] == (3, 11); assert json.load(open("/usr/share/frigate-rocm/runtime.json"))["profile"] == os.environ["FRIGATE_ROCM_PROFILE"]; import migraphx'
LABEL org.opencontainers.image.source="https://github.com/jaysqvl/frigate" \
    org.opencontainers.image.revision="${SOURCE_COMMIT}" \
    io.jaysqvl.frigate.runtime="${RUNTIME_IMAGE}" \
    io.jaysqvl.frigate.profile="${RUNTIME_PROFILE}" \
    io.jaysqvl.frigate.hardware-validation="required"

FROM rocm-general AS rocm-legacy
ENV MIGRAPHX_DISABLE_MIOPEN_FUSION=1 \
    MIGRAPHX_DISABLE_SCHEDULE_PASS=1 \
    MIGRAPHX_DISABLE_REDUCE_FUSION=1 \
    MIGRAPHX_ENABLE_HIPRTC_WORKAROUNDS=1

FROM rocm-legacy AS rocm-native
ENV FRIGATE_ROCM_NATIVE_GFX90C=1 \
    ROCBLAS_TENSILE_LIBPATH=/opt/rocm/lib/rocblas/library
