#!/bin/bash
#
# 启动 Alice SecretPad（可切换协议）
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
PAD_DIR="${PROJECT_DIR}/NewProject/secretpad"
PAD_KUSCIA_STATE_DIR="/tmp/secretpad-alice-local-kuscia"

JAVA_HOME="${JAVA_HOME:-/Library/Java/JavaVirtualMachines/zulu-21.jdk/Contents/Home}"
JAVA_BIN="${JAVA_HOME}/bin/java"

cd "${PAD_DIR}"

export SERVER_PORT=18443
export SERVER_HTTP_PORT=18080
export SERVER_HTTP_PORT_INNER=19001
export NODE_ID=alice
# Allow startup schema initialization alongside the job watch connection.
export SPRING_DATASOURCE_DEFAULT_MAXIMUM_POOL_SIZE=2
export INST_NAME=alice

# 协议切换配置（允许外部传入，供 switch_alice_protocol.sh 覆盖）
export SECRETPAD_PROTOCOL_DEFAULT="${SECRETPAD_PROTOCOL_DEFAULT:-secretflow}"
export SECRETPAD_PROTOCOL_CAN_SWITCH="true"
export SECRETPAD_PROTOCOL_STATE_FILE="${SECRETPAD_PROTOCOL_STATE_FILE:-${PAD_DIR}/protocol.state}"
export SECRETPAD_BFIA_CROSSNODE_ENABLED="true"
export SECRETPAD_BFIA_PEER_NODE_ID="${SECRETPAD_BFIA_PEER_NODE_ID:-bob}"

# 同一个 SecretPad 进程承载两种协议，因此运行时切换不能再替换数据库目录。
# 原生业务库沿用历史 db_secretflow；BFIA 专用库固定放在 db_bfia。
export DB_PATH="${DB_PATH:-${PAD_DIR}/db_secretflow}"
export HOST_PATH="${HOST_PATH:-${PAD_DIR}/data_secretflow/}"
export BFIA_DB_URL="${BFIA_DB_URL:-jdbc:h2:${PAD_DIR}/db_bfia/secretpad_bfia;DB_CLOSE_ON_EXIT=FALSE;MODE=MySQL;DATABASE_TO_LOWER=TRUE}"
PAD_LOG_DIR="${SECRETPAD_LOG_PATH:-/tmp/secretpad-log-alice}"
export SECRETPAD_LOG_PATH="${PAD_LOG_DIR}"
export SECRETPAD_LOGS_PATH="${PAD_LOG_DIR}"

mkdir -p "${DB_PATH}" "${HOST_PATH}" "${PAD_DIR}/db_bfia" "${PAD_LOG_DIR}" "${PAD_KUSCIA_STATE_DIR}"

# 兼容迁移：旧版统一 db/data 目录仅在隐语原生模式下迁移一次，避免已有数据丢失
LEGACY_DB_DIR="${PAD_DIR}/db"
LEGACY_DATA_DIR="${PAD_DIR}/data"
if [[ -d "${LEGACY_DB_DIR}" && ! -f "${DB_PATH}/secretpad.sqlite" ]]; then
  echo "[MIGRATE] 发现旧版未隔离数据库，复制到 ${DB_PATH} 以保留隐语原生数据 ..."
  cp -R "${LEGACY_DB_DIR}/"* "${DB_PATH}/"
fi
if [[ -d "${LEGACY_DATA_DIR}" && -z "$(ls -A "${HOST_PATH}" 2>/dev/null)" ]]; then
  echo "[MIGRATE] 发现旧版未隔离数据目录，复制到 ${HOST_PATH} 以保留隐语原生数据 ..."
  cp -R "${LEGACY_DATA_DIR}/"* "${HOST_PATH}/"
fi

# Alice 自身 Kuscia gRPC API
# 由于 macOS 宿主机无法直接访问 Docker 容器 IP 192.168.117.2，
# 通过 kusciaapi-alice-proxy 容器将 127.0.0.1:18083 转发到 Alice 的 8083。
export KUSCIA_API_ADDRESS="127.0.0.1"
export KUSCIA_API_PORT="18083"
export KUSCIA_PROTOCOL="tls"

# Kuscia 网关地址（P2P 数据同步使用）
export KUSCIA_GW_ADDRESS="198.18.2.76:80"

# BFIA 互联 HTTP API 地址
# macOS 宿主机无法直接访问 Docker 容器 IP，通过本地端口转发访问 Alice/Bob 的 8084。
export KUSCIA_API_LITE_ALICE_ADDRESS="127.0.0.1:18084"
export KUSCIA_API_LITE_BOB_ADDRESS="127.0.0.1:28084"
export KUSCIA_BFIA_HTTP_PORT="8084"

# 对端 SecretPad HTTP 地址（跨节点项目同步用）
export SECRETPAD_ALICE_HTTP_ADDRESS="localhost:18080"
export SECRETPAD_BOB_HTTP_ADDRESS="localhost:28090"
export SECRETPAD_PEER_KIMI_HTTP_ADDRESS="localhost:39001"

# BFIA 结果读取：Alice Kuscia 运行在 Docker 中，SecretPad 在 macOS 宿主机，
# 通过 docker exec 读取 /home/kuscia/var/storage 下的输出文件。
export SECRETPAD_BFIA_OUTPUT_STORAGE_TYPE="docker"
export SECRETPAD_BFIA_OUTPUT_DOCKER_CONTAINER="${USER}-kuscia-autonomy-alice"
export SECRETPAD_BFIA_INPUT_STORAGE_TYPE="${SECRETPAD_BFIA_INPUT_STORAGE_TYPE:-docker}"
export SECRETPAD_BFIA_INPUT_DOCKER_CONTAINER="${USER}-kuscia-autonomy-alice"

# PaddleDTX 本地演示桥接：SecretPad 在宿主机运行，requester CLI 在
# executor1.node.com 容器内运行。显式设置默认 wrapper 后，链桨页面的
# “发布并执行”不再只显示 health ready，而是可以真正提交 XChain 任务。
export PADDLEDTX_REQUESTER_COMMAND="${PADDLEDTX_REQUESTER_COMMAND:-${PROJECT_DIR}/NewProject/scripts/paddledtx-requester-wrapper.sh}"
export PADDLEDTX_REQUESTER_CONFIG="${PADDLEDTX_REQUESTER_CONFIG:-${PROJECT_DIR}/privacy-computing-interconnectivity/shared-exchange-Connectivity/PaddleDTX/testdata/executor/node1/conf/requester-config.toml}"
# 仅对本地演示启用。生产环境不设置该变量，仍执行 DTX 原生七天心跳健康门禁。
export PADDLEDTX_REQUESTER_BINARY="${PADDLEDTX_REQUESTER_BINARY:-/home/requester-cli-demo}"
export PADDLEDTX_DEMO_SKIP_HEALTH="${PADDLEDTX_DEMO_SKIP_HEALTH:-true}"

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
  -Dspring.jpa.show-sql=false \
  -Dspring.jpa.properties.hibernate.format_sql=false \
  -jar "${PAD_DIR}/target/secretpad.jar" \
  --spring.config.additional-location=file:./config/ \
  --secretpad.kuscia-path="${PAD_KUSCIA_STATE_DIR}/" \
  --secretpad.auth.enabled="${SECRETPAD_AUTH_ENABLED:-false}" \
  > "${PAD_LOG_DIR}/bootstrap.log" 2>&1
