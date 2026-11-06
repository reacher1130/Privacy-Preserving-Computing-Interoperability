#!/usr/bin/env bash
# Install only missing build tools; keep host-managed Docker packages and data.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'bootstrap requires root' >&2; exit 2; }
[[ -d /run/systemd/system ]] || { echo 'A Linux systemd host is required.' >&2; exit 2; }
. /etc/os-release
export DEBIAN_FRONTEND=noninteractive
if command -v apt-get >/dev/null; then
  apt-get update
  apt-get install -y ca-certificates curl git rsync tar gzip xz-utils unzip openssl nginx python3-yaml ripgrep iproute2 util-linux
  if ! command -v docker >/dev/null; then
    [[ "$ID" == ubuntu || "$ID" == debian ]] || { echo 'Install Docker for this distribution first.' >&2; exit 2; }
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/%s %s stable\n' "$(dpkg --print-architecture)" "$ID" "${UBUNTU_CODENAME:-$VERSION_CODENAME}" > /etc/apt/sources.list.d/ppci-docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  fi
elif command -v dnf >/dev/null; then
  dnf install -y ca-certificates curl git rsync tar gzip xz unzip openssl nginx python3-pyyaml iproute util-linux policycoreutils-python-utils
  # EPEL is not enabled automatically; a small rg release is installed below if needed.
  if ! command -v docker >/dev/null; then
    curl -fsSL https://download.docker.com/linux/centos/docker-ce.repo -o /etc/yum.repos.d/ppci-docker.repo
    dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin
  fi
else
  echo 'Automatic dependencies require Ubuntu/Debian apt or a maintained CentOS/RHEL-family dnf host.' >&2
  exit 2
fi
systemctl enable --now docker
python3 "$(dirname "$0")/portable.py" install-tools --native
