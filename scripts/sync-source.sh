#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
git submodule sync --recursive
git submodule update --init --recursive
python3 scripts/verify-source.py
python3 scripts/apply-source-patches.py
