#!/usr/bin/env bash
# Runs only the audited public fixtures. Deployment supplies the private result root.
set -euo pipefail
umask 077
export PATH=/opt/ppci-tools/rg:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
id="${1:-}"
[[ $# == 1 && "$id" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 2
root="${PPCI_BFIA_SUITE_ROOT:?Missing private result root}"
run="$root/runs/$id"
[[ "$root" == /* && -d "$run" && ! -L "$run" && ! -e "$run/exit-code" ]] || exit 2
runtime="${PPCI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
sf="$runtime/NewProject/secretflow"
python_tag="${BFIA_PYTHON_IMAGE:-ppci/bfia-python:amd64-20260908}"
cpp_tag="${BFIA_CPP_IMAGE:-ppci/bfia-cpp:numerics-20260914-v2}"
rg_bin="${PPCI_RG_BINARY:-/opt/ppci-tools/rg/rg}"
[[ -x "$rg_bin" ]] || rg_bin="$(command -v rg)"
python_name="ppci-bfia-python-$id"
cpp_algorithms=(ecdh-psi ss-lr ss-xgb ss-pearson ss-vif ss-compare)

finish() {
  local status=$?
  trap - EXIT
  if [[ "${started:-}" == 1 && "$status" != 0 ]]; then
    # A timeout can interrupt a Docker CLI before its own cleanup trap runs.
    local names=("$python_name")
    local algo
    for algo in "${cpp_algorithms[@]}"; do
      names+=("bfia-cpp-$id-$algo-alice" "bfia-cpp-$id-$algo-bob")
    done
    timeout 10s docker rm -f "${names[@]}" >/dev/null 2>&1 || true
    timeout 10s docker network rm "bfia-cpp-$id" >/dev/null 2>&1 || true
  fi
  printf '%s\n' "$status" >"$run/.exit-code.tmp"
  mv -T "$run/.exit-code.tmp" "$run/exit-code"
  exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

exec 9>"$root/runner.lock"
flock -n 9 || { echo 'BFIA suite is already running on this host' >&2; exit 75; }
[[ ! -e "$run/python" && ! -e "$run/cpp" ]] || exit 2
[[ -x "$rg_bin" && -f "$sf/bfia/run_audited_cpp_tests.sh" ]]
python_image="$(docker image inspect --format '{{.Id}}' "$python_tag")"
cpp_image="$(docker image inspect --format '{{.Id}}' "$cpp_tag")"
printf 'python_image=%s cpp_image=%s\n' "$python_image" "$cpp_image"
started=1

python_status=0
timeout --kill-after=10s 280s docker run --rm --pull=never --name "$python_name" \
  --cpus=4 --memory=4g --network=none \
  -v "$sf:$sf:ro" -v "$run:$run" -v "$rg_bin:/usr/local/bin/rg:ro" -w "$sf" \
  -e BFIA_RUN_ID="$id" -e BFIA_RESULT_ROOT="$run" -e BFIA_TIMEOUT_SEC=120 \
  -e BFIA_PYTHON_ALICE_IP=127.0.0.1 -e BFIA_PYTHON_BOB_IP=127.0.0.2 \
  -e PYTHONDONTWRITEBYTECODE=1 -e OMP_NUM_THREADS=2 -e OPENBLAS_NUM_THREADS=2 \
  --entrypoint bash "$python_image" bfia/run_python_tests.sh || python_status=$?
if (( python_status != 0 )); then
  timeout 10s docker rm -f "$python_name" >/dev/null 2>&1 || true
fi

cpp_status=0
timeout --kill-after=15s 390s env -i PATH="$PATH" BFIA_RUN_ID="$id" BFIA_RESULT_ROOT="$run" \
  BFIA_CPP_IMAGE="$cpp_image" BFIA_CPP_RUNTIME=docker BFIA_CPP_BINARY_IN_DOCKER=0 \
  BFIA_CPP_TIMEOUT_SEC=55 BFIA_VALIDATOR_IMAGE="$python_image" \
  bash "$sf/bfia/run_audited_cpp_tests.sh" || cpp_status=$?
printf 'python_exit=%s cpp_exit=%s\n' "$python_status" "$cpp_status"
(( python_status == 0 && cpp_status == 0 ))
