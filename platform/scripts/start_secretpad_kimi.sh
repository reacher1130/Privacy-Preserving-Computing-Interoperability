#!/bin/bash
#
# 启动 Kimi SecretPad（固定隐语原生协议）
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PAD_DIR="${PROJECT_DIR}/NewProject/secretpad-kimi-upstream"
PAD_LOG_DIR="/tmp/secretpad-kimi-log"

JAVA_HOME="${JAVA_HOME:-/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home}"
JAVA_BIN="${JAVA_HOME}/bin/java"

mkdir -p "${PAD_LOG_DIR}"
cd "${PAD_DIR}"

export SERVER_PORT=38443
export SERVER_HTTP_PORT=38090
export SERVER_HTTP_PORT_INNER=39001
export SECRETPAD_LOG_PATH="${PAD_LOG_DIR}"
export NODE_ID=kimi
export INST_NAME=kimi
export HOST_PATH="${HOST_PATH:-${PAD_DIR}/data/}"

# Kimi 自身 Kuscia gRPC API
export KUSCIA_API_ADDRESS="127.0.0.1"
export KUSCIA_API_PORT="38083"
export KUSCIA_PROTOCOL="tls"

export KUSCIA_GW_ADDRESS="192.168.117.4:80"
export SECRETPAD_PEER_ALICE_HTTP_ADDRESS="localhost:19001"

# 协议切换配置：Kimi 固定隐语原生，不可切换
export SECRETPAD_PROTOCOL_DEFAULT="secretflow"
export SECRETPAD_PROTOCOL_CAN_SWITCH="false"
export SECRETPAD_PROTOCOL_STATE_FILE="${SECRETPAD_PROTOCOL_STATE_FILE:-${PAD_DIR}/protocol.state}"

# 兼容账号（仅 SECRETPAD_AUTH_ENABLED=true 时使用；演示免登录不读取）
export SECRETPAD_USER_NAME="${SECRETPAD_USER_NAME:-admin}"
export SECRETPAD_PASSWORD="${SECRETPAD_PASSWORD:-secretPad@123}"

# Bound the heap and worker count for the three local demonstration backends.
exec "${JAVA_BIN}" \
  -Xms128m -Xmx"${SECRETPAD_JAVA_HEAP_MAX:-768m}" \
  -XX:ReservedCodeCacheSize=128m -XX:ActiveProcessorCount=2 \
  -XX:G1PeriodicGCInterval=60000 -XX:+UseStringDeduplication \
  -XX:MinHeapFreeRatio=20 -XX:MaxHeapFreeRatio=40 \
  -Dserver.tomcat.accesslog.enabled=false \
  -Dspring.profiles.active=p2p \
  -Dserver.port="${SERVER_PORT}" \
  -Dserver.http-port="${SERVER_HTTP_PORT}" \
  -Dserver.http-port-inner="${SERVER_HTTP_PORT_INNER}" \
  -jar "${PAD_DIR}/target/secretpad.jar" \
  --secretpad.auth.enabled="${SECRETPAD_AUTH_ENABLED:-false}" \
  > "${PAD_LOG_DIR}/bootstrap.log" 2>&1
