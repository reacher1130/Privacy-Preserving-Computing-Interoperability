#!/bin/bash
#
# 启动 Bob SecretPad（固定 BFIA 协议）
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PAD_DIR="${PROJECT_DIR}/NewProject/secretpad-bob"
PAD_LOG_DIR="/tmp/secretpad-bob-log"
PAD_KUSCIA_STATE_DIR="/tmp/secretpad-bob-local-kuscia"

JAVA_HOME="${JAVA_HOME:-/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home}"
JAVA_BIN="${JAVA_HOME}/bin/java"

mkdir -p "${PAD_LOG_DIR}" "${PAD_KUSCIA_STATE_DIR}"
cd "${PAD_DIR}"

# 使用当前容器 CA 签发的 PKCS#8 客户端身份，不覆盖历史部署证书。
BOB_KUSCIA_CONTAINER="${BOB_KUSCIA_CONTAINER:-${USER}-kuscia-autonomy-bob}"
if ! docker exec "${BOB_KUSCIA_CONTAINER}" test -s /home/kuscia/var/certs/kusciaapi-client.crt; then
  docker exec "${BOB_KUSCIA_CONTAINER}" bash scripts/deploy/init_kusciaapi_client_certs.sh
fi
mkdir -p config/certs/bob-local
docker cp "${BOB_KUSCIA_CONTAINER}:/home/kuscia/var/certs/kusciaapi-client.crt" config/certs/bob-local/client.crt
docker cp "${BOB_KUSCIA_CONTAINER}:/home/kuscia/var/certs/kusciaapi-client.key" config/certs/bob-local/client.pem
docker cp "${BOB_KUSCIA_CONTAINER}:/home/kuscia/var/certs/token" config/certs/bob-local/token
chmod 600 config/certs/bob-local/client.pem config/certs/bob-local/token

export SERVER_PORT=28443
export SERVER_HTTP_PORT=28090
export SERVER_HTTP_PORT_INNER=29001
export SECRETPAD_LOG_PATH="${PAD_LOG_DIR}"
export NODE_ID=bob
export INST_NAME=bob
# Keep the Quartz/SQLite runtime files outside the source checkout.  The
# local code indexer may open repository database files while scanning, which
# can make H2 refuse a second embedded connection with a file-lock error.  The
# BFIA store remains the explicit `BFIA_DB_URL` below and is not relocated.
export DB_PATH="${DB_PATH:-/tmp/secretpad-bob-runtime}"
export HOST_PATH="${HOST_PATH:-${PAD_DIR}/data_bfia/}"
mkdir -p "${DB_PATH}" "${HOST_PATH}"

# Bob 自身 Kuscia gRPC API
export KUSCIA_API_ADDRESS="127.0.0.1"
export KUSCIA_API_PORT="28083"
export KUSCIA_PROTOCOL="tls"

# BFIA 互联 HTTP API 地址（宿主机通过本地端口转发访问容器 8084）
export KUSCIA_API_LITE_ALICE_ADDRESS="127.0.0.1:18084"
export KUSCIA_API_LITE_BOB_ADDRESS="127.0.0.1:28084"
export KUSCIA_BFIA_HTTP_PORT="8084"

# 对端 SecretPad HTTP 地址（跨节点项目同步用）
export SECRETPAD_ALICE_HTTP_ADDRESS="localhost:18080"
export SECRETPAD_BOB_HTTP_ADDRESS="localhost:28090"

# 协议切换配置：Bob 固定 BFIA，不可切换
export SECRETPAD_PROTOCOL_DEFAULT="bfia"
export SECRETPAD_PROTOCOL_CAN_SWITCH="false"
export SECRETPAD_PROTOCOL_STATE_FILE="${SECRETPAD_PROTOCOL_STATE_FILE:-${PAD_DIR}/protocol.state}"
export SECRETPAD_BFIA_CROSSNODE_ENABLED="true"
export SECRETPAD_BFIA_PEER_NODE_ID="${SECRETPAD_BFIA_PEER_NODE_ID:-alice}"

# BFIA H2 数据库
export BFIA_DB_URL="jdbc:h2:./db/secretpad_bfia;DB_CLOSE_ON_EXIT=FALSE;MODE=MySQL;DATABASE_TO_LOWER=TRUE"
export BFIA_DB_USER="sa"
export BFIA_DB_PASSWORD="password"

# BFIA 结果读取：Bob Kuscia 运行在 Docker 中，SecretPad 在 macOS 宿主机。
export SECRETPAD_BFIA_OUTPUT_STORAGE_TYPE="docker"
export SECRETPAD_BFIA_OUTPUT_DOCKER_CONTAINER="${USER}-kuscia-autonomy-bob"
export SECRETPAD_BFIA_INPUT_STORAGE_TYPE="docker"
export SECRETPAD_BFIA_INPUT_DOCKER_CONTAINER="${USER}-kuscia-autonomy-bob"

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
  -Dspring.profiles.active=bfia-bob \
  -jar "${PAD_DIR}/target/secretpad.jar" \
  --spring.config.additional-location=file:./config/ \
  --secretpad.kuscia-path="${PAD_KUSCIA_STATE_DIR}/" \
  --secretpad.auth.enabled="${SECRETPAD_AUTH_ENABLED:-false}" \
  > "${PAD_LOG_DIR}/bootstrap.log" 2>&1
