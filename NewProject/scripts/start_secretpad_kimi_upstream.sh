#!/bin/bash
#
# 启动 Kimi 上游官方 SecretPad（固定隐语原生协议 P2P）
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PAD_DIR="${PROJECT_DIR}/NewProject/secretpad-kimi-upstream"
PAD_LOG_DIR="/tmp/secretpad-kimi-upstream-log"

JAVA_HOME="${JAVA_HOME:-/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home}"
JAVA_BIN="${JAVA_HOME}/bin/java"

mkdir -p "${PAD_LOG_DIR}"
cd "${PAD_DIR}"

# Spring Boot 端口通过命令行参数传入（上游 application.yaml 未使用 SERVER_PORT 环境变量）
SERVER_PORT=38443
SERVER_HTTP_PORT=38090
SERVER_HTTP_PORT_INNER=39001

export SECRETPAD_LOG_PATH="${PAD_LOG_DIR}"
export NODE_ID=kimi
export INST_NAME=kimi
export HOST_PATH="${PAD_DIR}/data/"

# Kuscia 网关地址（P2P 数据同步使用）
export KUSCIA_GW_ADDRESS="192.168.117.4:80"

# Kimi 自身 Kuscia gRPC API
# macOS 宿主机无法直接访问 Docker 容器 IP，通过 kusciaapi-kimi-proxy 容器
# 将 127.0.0.1:38083 转发到 Kimi 的 8083。
export KUSCIA_API_ADDRESS="127.0.0.1"
export KUSCIA_API_PORT="38083"
export KUSCIA_PROTOCOL="tls"

# 对端 SecretPad HTTP 地址（跨节点项目同步用）
export SECRETPAD_PEER_ALICE_HTTP_ADDRESS="localhost:19001"

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
