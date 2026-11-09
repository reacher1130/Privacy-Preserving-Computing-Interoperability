#!/usr/bin/env bash
# The fixed image contains the code and dependencies; Kuscia owns the task process.
set -euo pipefail
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[[ $# == 1 && "$1" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]] || exit 2
runtime="${PPCI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
python="${PPCI_PYTHON:-python3}"
exec "$python" "$runtime/NewProject/scripts/environments/bfia-suite-kuscia.py" run "$1" --runtime-root "$runtime"
