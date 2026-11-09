#!/bin/bash
#
# 启动 Alice 上游官方 SecretPad（固定隐语原生协议 P2P）
# 与 Kimi 上游同源，使用官方隐语前端样式。
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PAD_DIR="${PROJECT_DIR}/NewProject/secretpad-alice-upstream"
PAD_LOG_DIR="/tmp/secretpad-alice-upstream-log"

JAVA_HOME="${JAVA_HOME:-/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home}"
JAVA_BIN="${JAVA_HOME}/bin/java"

mkdir -p "${PAD_LOG_DIR}"
cd "${PAD_DIR}"

SERVER_PORT=18443
SERVER_HTTP_PORT=18080
SERVER_HTTP_PORT_INNER=19001

export SECRETPAD_LOG_PATH="${PAD_LOG_DIR}"
export NODE_ID=alice
export INST_NAME=alice
export HOST_PATH="${PAD_DIR}/data/"

# Kuscia 网关地址（P2P 数据同步使用）
export KUSCIA_GW_ADDRESS="192.168.117.2:80"

# Alice 自身 Kuscia gRPC API
export KUSCIA_API_ADDRESS="192.168.117.2"
export KUSCIA_API_PORT="8083"
export KUSCIA_PROTOCOL="tls"

# 对端 SecretPad HTTP 地址（跨节点项目同步用）
export SECRETPAD_PEER_KIMI_HTTP_ADDRESS="localhost:39001"

# 登录账号
export SECRETPAD_USER_NAME="${SECRETPAD_USER_NAME:-admin}"
export SECRETPAD_PASSWORD="${SECRETPAD_PASSWORD:-secretPad@123}"

exec "${JAVA_BIN}" \
  -Dserver.tomcat.accesslog.enabled=false \
  -Dspring.profiles.active=p2p \
  -Dserver.port="${SERVER_PORT}" \
  -Dserver.http-port="${SERVER_HTTP_PORT}" \
  -Dserver.http-port-inner="${SERVER_HTTP_PORT_INNER}" \
  -jar "${PAD_DIR}/target/secretpad.jar" \
  --secretpad.auth.enabled="${SECRETPAD_AUTH_ENABLED:-false}" \
  > "${PAD_LOG_DIR}/secretpad.log" 2> "${PAD_LOG_DIR}/error.log"
