#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="${IMAGE_NAME:-secretflow/fate2-adapter:0.2.0-native}"
PLATFORM="${PLATFORM:-linux/amd64}"

cd "${PROJECT_DIR}"

echo "[BUILD] Building fate2-adapter image: ${IMAGE_NAME} (${PLATFORM})"
docker build --platform "${PLATFORM}" -t "${IMAGE_NAME}" -f scripts/Dockerfile .

echo "[BUILD] Done: ${IMAGE_NAME}"
