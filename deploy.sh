#!/usr/bin/env bash
# Full portable deployment entry. Run --help before installing a new host.
set -euo pipefail
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v python3 >/dev/null 2>&1; then
  case "${1:-all}" in
    all|bootstrap)
      [[ $(id -u) == 0 ]] || { echo 'Run with sudo to install Python 3.' >&2; exit 2; }
      if command -v apt-get >/dev/null; then apt-get update; apt-get install -y python3
      elif command -v dnf >/dev/null; then dnf install -y python3
      else echo 'Install Python >= 3.9 first.' >&2; exit 2; fi ;;
    *) echo 'Python >= 3.9 is required.' >&2; exit 2 ;;
  esac
fi
exec python3 scripts/portable.py "$@"
