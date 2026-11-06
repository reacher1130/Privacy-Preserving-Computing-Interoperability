#!/usr/bin/env bash
set -euo pipefail
ROOT="${PPCI_ROOT:-/opt/ppci}"
SF="$ROOT/NewProject/secretflow"
MODE="${1:-all}"
SOURCE="${PPCI_SOURCE_ROOT:-/opt/ppci-source}"
# Materialize source beside the existing Linux caches. Never touch platform data.
if [[ -d "$SOURCE/NewProject/secretflow" && "$SOURCE" != "$ROOT" ]]; then
  for file in secretflow/bfia/run_all_tests.sh secretflow/interconnection-impl/.cache/patch_all_bzl.py yacl/WORKSPACE; do
    [[ -f "$SOURCE/NewProject/$file" ]] || { echo "Incomplete Git source checkout: $file" >&2; exit 2; }
  done
  [[ -d "$SOURCE/NewProject/secretflow/interconnection-impl/.cache/overridden" ]] || { echo 'Missing C++ source overrides' >&2; exit 2; }
  rsync -a --delete --exclude=.git --exclude=.cache --exclude=__pycache__ \
    --exclude=/bfia/results/ --exclude=/interconnection-impl/ic_impl/data/ --exclude='/interconnection-impl/bazel-*' \
    "$SOURCE/NewProject/secretflow/" "$SF/"
  rsync -a --delete --exclude=/bazel-home --exclude=/bazelisk --exclude=/deps \
    "$SOURCE/NewProject/secretflow/interconnection-impl/.cache/" "$SF/interconnection-impl/.cache/"
  rsync -a --delete --exclude=.git --exclude='.cache' --exclude='bazel-*' \
    "$SOURCE/NewProject/yacl/" "$ROOT/NewProject/yacl/"
fi
export BFIA_RUN_ID="${BFIA_RUN_ID:-remote-$(date +%Y%m%d-%H%M%S)}"
python_tests() {
  docker run --rm --cpus=4 --memory=4g \
    -v "$SF:$SF" -v /opt/ppci-tools/rg/rg:/usr/local/bin/rg:ro -w "$SF" \
    -e BFIA_RUN_ID -e BFIA_TIMEOUT_SEC=600 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
    --entrypoint bash ppci/bfia-python:amd64-20260908 \
    -c 'export BFIA_PYTHON_ALICE_IP=127.0.0.1; export BFIA_PYTHON_BOB_IP=$(hostname -i | awk "{print \$1}"); exec bash bfia/run_python_tests.sh'
}
cpp_tests() {
  BFIA_CPP_IMAGE="${BFIA_CPP_IMAGE:-ppci/bfia-cpp:numerics-20260914-v2}" BFIA_CPP_RUNTIME=docker BFIA_CPP_BINARY_IN_DOCKER=0 bash "$SF/bfia/run_audited_cpp_tests.sh"
}
case "$MODE" in
  python) python_tests ;;
  cpp) cpp_tests ;;
  all) status=0; python_tests || status=$?; cpp_tests || status=$?; exit "$status" ;;
  build-cpp)
    bash "$SF/interconnection-impl/docker/build_ic_main_local.sh"
    DOCKER_BUILDKIT=0 bash "$SF/interconnection-impl/docker/build_cpp_runtime_slim.sh"
    ;;
  *) echo 'Usage: algorithms.sh [all|python|cpp|build-cpp]' >&2; exit 2 ;;
esac
