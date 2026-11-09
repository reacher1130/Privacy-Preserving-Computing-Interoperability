#!/usr/bin/env bash
# Regression for the lib25519 build/header fix; run after build-cpp prepares its dependencies.
set -euo pipefail
SF="${PPCI_ROOT:-/opt/ppci}/NewProject/secretflow"
CACHE="$SF/interconnection-impl/.cache"
docker run --rm --cpus=4 --memory=6g --entrypoint bash \
  -v "$SF:/secretflow" -v "$CACHE/bazelisk:/opt/bazel:ro" \
  -v "$CACHE/bazel-home:/root/.cache/bazel" \
  -w /secretflow/interconnection-impl \
  secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/morse-ecdh-header:20251113 \
  -c '/opt/bazel/bazel-6.5.0-linux-x86_64 test -c opt \
    --jobs=4 --local_cpu_resources=4 --local_ram_resources=4096 \
    --spawn_strategy=standalone --test_output=errors --dynamic_mode=off --linkopt=-lm \
    --override_repository=com_envoyproxy_protoc_gen_validate=/secretflow/interconnection-impl/.cache/overridden/com_envoyproxy_protoc_gen_validate \
    --override_repository=com_google_googletest=/secretflow/interconnection-impl/.cache/overridden/com_google_googletest \
    --override_repository=com_github_intel_ipp=/secretflow/interconnection-impl/.cache/overridden/com_github_intel_ipp \
    @yacl//yacl/crypto/ecc/lib25519:ed25519_test'
