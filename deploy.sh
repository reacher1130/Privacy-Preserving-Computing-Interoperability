#!/usr/bin/env bash
# Full portable deployment entry. Run --help before installing a new host.
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
find_python() {
  for candidate in "${PPCI_PYTHON:-}" python3.12 python3.11 python3.10 python3.9 python3; do
    [[ -n "$candidate" ]] || continue
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 9))' 2>/dev/null; then
      PPCI_PYTHON="$(command -v "$candidate")"
      export PPCI_PYTHON
      return
    fi
  done
  return 1
}
if ! find_python; then
  case "${1:-all}" in
    all|bootstrap|build)
      [[ $(id -u) == 0 ]] || { echo 'Run with sudo to install Python 3.' >&2; exit 2; }
      if command -v apt-get >/dev/null; then apt-get update; apt-get install -y python3
      elif command -v dnf >/dev/null; then dnf install -y python3.11 python3.11-pip
      else echo 'Install Python >= 3.9 first.' >&2; exit 2; fi ;;
    *) echo 'Python >= 3.9 is required.' >&2; exit 2 ;;
  esac
fi
find_python || { echo 'Python >= 3.9 is required.' >&2; exit 2; }
exec "$PPCI_PYTHON" scripts/portable.py "$@"
