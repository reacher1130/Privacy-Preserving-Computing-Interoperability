#!/usr/bin/env bash
# Install runtime dependencies by default; compilation tools require explicit build mode.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'bootstrap requires root' >&2; exit 2; }
[[ -d /run/systemd/system ]] || { echo 'A Linux systemd host is required.' >&2; exit 2; }
. /etc/os-release
mode="${1:-runtime}"
[[ "$mode" == runtime || "$mode" == build ]] || { echo 'Usage: install-deps.sh [runtime|build]' >&2; exit 2; }
python="${PPCI_PYTHON:-python3}"
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null; then
  apt-get update
  apt-get install -y --no-install-recommends ca-certificates curl git rsync tar gzip xz-utils unzip openssl nginx python3-yaml python3-pip ripgrep iproute2 util-linux
  if ! command -v docker >/dev/null; then
    [[ "$ID" == ubuntu || "$ID" == debian ]] || { echo 'Install Docker for this distribution first.' >&2; exit 2; }
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' "$(dpkg --print-architecture)" "$ID" "${UBUNTU_CODENAME:-$VERSION_CODENAME}" > /etc/apt/sources.list.d/ppci-docker.list
    apt-get update
    apt-get install -y --no-install-recommends docker-ce docker-ce-cli containerd.io
  fi
elif command -v dnf >/dev/null; then
  dnf install -y ca-certificates curl git rsync tar gzip xz unzip openssl nginx iproute util-linux policycoreutils-python-utils python3-pip python3-pyyaml
  # EPEL is not enabled automatically; a small rg release is installed below if needed.
  if ! command -v docker >/dev/null; then
    curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo -o /etc/yum.repos.d/ppci-docker.repo
    dnf install -y docker-ce docker-ce-cli containerd.io
  fi
else
  echo 'Automatic dependencies require Ubuntu/Debian apt or a maintained CentOS/RHEL-family dnf host.' >&2
  exit 2
fi
systemctl enable --now docker
if ! "$python" -c 'import yaml' >/dev/null 2>&1; then
  if ! "$python" -m pip --version >/dev/null 2>&1; then
    "$python" -m ensurepip --upgrade
  fi
  "$python" -m pip install --only-binary=:all: 'PyYAML==6.0.3'
fi
tool_action=install-runtime
[[ "$mode" != build ]] || tool_action=install-tools
"$python" "$(dirname "$0")/portable.py" "$tool_action" --native
