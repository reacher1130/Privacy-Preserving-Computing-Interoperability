#!/bin/bash
#
# Alice Kuscia 协议切换脚本
#
# 用法:
#   ./switch_alice_protocol.sh bfia       # 切换到 BFIA 协议，准备与 Bob 互通
#   ./switch_alice_protocol.sh kuscia     # 切换到隐语原生协议，准备与 Kimi 互通
#   ./switch_alice_protocol.sh secretflow # 同 kuscia
#
# 说明:
#   - Alice 使用同一套支持 Kuscia/BFIA 的运行时，不为切换而中断容器
#   - 在 Alice 和目标对端注册对应 AppImage，并重建、校验 DomainRoute
#   - 默认不重启 SecretPad；仅手工设置 RESTART_PAD=true 时兼容旧流程
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NEWPROJECT_DIR="${PROJECT_DIR}/NewProject"
KUSCIA_DIR="${NEWPROJECT_DIR}/kuscia"

PROTOCOL="${1:-kuscia}"
CONTAINER_NAME="${USER}-kuscia-autonomy-alice"
NETWORK_NAME="kuscia-exchange"
KUSCIA_IMAGE="${KUSCIA_IMAGE:-secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/kuscia:1.2.0b0}"
SECRETFLOW_IMAGE="${SECRETFLOW_IMAGE:-secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/secretflow-lite-anolis8:1.11.0b1}"

# 对端配置
BOB_CTR="${USER}-kuscia-autonomy-bob"
BOB_DOMAIN="bob"
BOB_IP="192.168.117.3"
KIMI_CTR="${USER}-kuscia-autonomy-kimi"
KIMI_DOMAIN="kimi"
KIMI_IP="192.168.117.4"

# 协议规范化。FATE 只在 Alice 本地调度适配器，原生 FATE 自行处理跨方通信。
case "${PROTOCOL}" in
  secretflow|native)
    PROTOCOL="kuscia"
    ;;
  bfia|kuscia|fate)
    ;;
  *)
    echo "[ERROR] 不支持的协议: ${PROTOCOL}，仅支持 bfia / kuscia / secretflow / fate"
    exit 1
    ;;
esac

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()  { echo -e "${GREEN}[SWITCH]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1"; }

get_container_ip() {
  docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$1" 2>/dev/null | head -1
}

ensure_network() {
  if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
    docker network create "${NETWORK_NAME}"
    log "创建 Docker 网络: ${NETWORK_NAME}"
  fi
}

# 确保 Alice 配置目录存在（保留现有 kuscia.yaml，避免证书变化）
ensure_alice_config() {
  local alice_dir="${PROJECT_DIR}/${CONTAINER_NAME}"
  mkdir -p "${alice_dir}/images"

  if [[ ! -f "${alice_dir}/kuscia.yaml" ]] || [[ -d "${alice_dir}/kuscia.yaml" ]]; then
    [[ -d "${alice_dir}/kuscia.yaml" ]] && rm -rf "${alice_dir}/kuscia.yaml"
    docker run --rm "${KUSCIA_IMAGE}" kuscia init --mode autonomy --domain alice > "${alice_dir}/kuscia.yaml"
    # Alice 需要同时支持 BFIA 和原生，默认注入 BFIA 插件（不影响原生协议）
    cat >> "${alice_dir}/kuscia.yaml" <<'EOF'
agent:
  allowPrivileged: true
  plugins:
    - name: cert-issuance
    - name: config-render
    - name: env-import
      config:
        usePodLabels: false
        envList:
          - envs:
              - name: system.transport
                value: transport.alice.svc
              - name: system.storage
                value: file:///home/kuscia/var/storage
              - name: system.storage.localfile
                value: file:///home/kuscia/var/storage
            selectors:
              - key: maintainer
                value: secretflow-contact@service.alipay.com
EOF
    log "已生成 Alice 初始配置: ${alice_dir}/kuscia.yaml"
  else
    log "保留现有 Alice kuscia.yaml（避免 domain 证书变化）"
  fi
}

# 停止现有容器（不删除，保留 k3s 等 overlay 数据）
stop_alice_container() {
  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "停止 Alice Kuscia 容器: ${CONTAINER_NAME}"
    docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
  fi
}

# 启动已有容器
start_alice_container() {
  local alice_dir="${PROJECT_DIR}/${CONTAINER_NAME}"

  if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    log "Alice Kuscia 容器已运行，保持现有任务运行时"
    return 0
  elif ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    local volume_name="${CONTAINER_NAME}-containerd"
    local hostname
    hostname=$(echo "${CONTAINER_NAME}-$(hostname)" | cut -c 1-63 | tr '[:upper:]_.' '[:lower:]--' | sed 's/^[^a-z0-9]//; s/[^a-z0-9]$//g')

    ensure_network
    docker volume inspect "${volume_name}" >/dev/null 2>&1 || docker volume create "${volume_name}"

    log "创建并启动 Alice Kuscia 容器 (${PROTOCOL} 模式) ..."
    docker run -dit --name="${CONTAINER_NAME}" \
      --hostname="${hostname}" \
      --restart=always \
      --network="${NETWORK_NAME}" \
      --ip="192.168.117.2" \
      --privileged \
      -v "${volume_name}:/home/kuscia/containerd" \
      -v "${alice_dir}/kuscia.yaml:/home/kuscia/etc/conf/kuscia.yaml" \
      -v "${alice_dir}/images:/home/kuscia/var/images" \
      "${KUSCIA_IMAGE}" bin/kuscia start -c etc/conf/kuscia.yaml
  else
    log "启动已有 Alice Kuscia 容器 (${PROTOCOL} 模式) ..."
    docker start "${CONTAINER_NAME}" >/dev/null 2>&1
  fi
}

# 等待 Kuscia 就绪
wait_for_kuscia() {
  local ctr="${1:-${CONTAINER_NAME}}"
  log "等待 ${ctr} Kuscia 就绪 ..."
  local retry=0
  while [[ "${retry}" -lt 60 ]]; do
    local code
    code=$(docker exec "${ctr}" curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:6443 2>/dev/null | tr -d '\r\n' || echo "000")
    if [[ "${code}" == "200" || "${code}" == "401" || "${code}" == "403" ]]; then
      log "Kuscia API 已就绪"
      return 0
    fi
    sleep 2
    retry=$((retry + 1))
  done
  err "${ctr} Kuscia 启动超时"
  return 1
}

# 等待 Kuscia CRD 就绪
wait_for_kuscia_crds() {
  local ctr="${1:-${CONTAINER_NAME}}"
  log "等待 ${ctr} Kuscia CRD 就绪 ..."
  local retry=0
  while [[ "${retry}" -lt 60 ]]; do
    if docker exec "${ctr}" kubectl get crd appimages.kuscia.secretflow >/dev/null 2>&1; then
      log "Kuscia CRD 已就绪"
      return 0
    fi
    sleep 2
    retry=$((retry + 1))
  done
  err "Kuscia CRD 等待超时"
  return 1
}

# 目标容器必须存在且正在运行；切换不能悄悄降级成半配置状态。
ensure_container_running() {
  local ctr="$1"
  if ! docker ps -a --format '{{.Names}}' | grep -q "^${ctr}$"; then
    err "目标 Kuscia 容器不存在: ${ctr}"
    return 1
  fi
  if ! docker ps --format '{{.Names}}' | grep -q "^${ctr}$"; then
    log "启动 Kuscia 容器: ${ctr}"
    docker start "${ctr}" >/dev/null
  fi
}

# 注册 Secretflow 原生 AppImage
register_secretflow_appimage() {
  local ctr="$1"
  log "在 ${ctr} 注册隐语原生 Secretflow AppImage ..."
  docker exec "${ctr}" scripts/deploy/register_app_image.sh -i "${SECRETFLOW_IMAGE}" -m
  docker exec "${ctr}" kubectl get appimage secretflow-image >/dev/null
}

# 注册 BFIA AppImage
register_bfia_appimages() {
  local ctr="$1"
  log "在 ${ctr} 注册 BFIA AppImage ..."
  local bfia_yaml_dir="${KUSCIA_DIR}/scripts/user/bfia"
  if [[ ! -d "${bfia_yaml_dir}" ]]; then
    err "BFIA YAML 目录不存在: ${bfia_yaml_dir}"
    return 1
  fi
  local manifests=() app_images=()
  for yaml in "${bfia_yaml_dir}"/ic-*.yaml; do
    [[ -f "${yaml}" ]] || continue
    manifests+=("${yaml}")
    app_images+=("$(awk '/^  name:/{print $2; exit}' "${yaml}")")
  done
  [[ "${#manifests[@]}" -gt 0 ]] || { err "BFIA YAML 为空"; return 1; }
  # Submit every manifest in one kubectl process; retain all algorithm registrations.
  { for yaml in "${manifests[@]}"; do cat "${yaml}"; printf '\n---\n'; done; } |
    docker exec -i "${ctr}" kubectl --request-timeout=60s apply -f - >/dev/null
  docker exec "${ctr}" kubectl --request-timeout=60s get appimage "${app_images[@]}" >/dev/null
}

# 在指定容器创建/更新 ClusterDomainRoute（带 endpoint），
# Domain 控制器与 clusterdomainroute 控制器会自动创建/同步 DomainRoute。
apply_clusterdomainroute() {
  local ctr="$1"
  local src="$2"
  local dst="$3"
  local dst_ip="$4"
  local proto="$5"

  docker exec -i "${ctr}" kubectl apply -f - <<EOF
apiVersion: kuscia.secretflow/v1alpha1
kind: ClusterDomainRoute
metadata:
  name: ${src}-${dst}
spec:
  source: ${src}
  destination: ${dst}
  interConnProtocol: ${proto}
  authenticationType: Token
  tokenConfig:
    tokenGenMethod: RSA-GEN
    rollingUpdatePeriod: 86400
  endpoint:
    host: ${dst_ip}
    ports:
      - name: http
        port: 1080
        protocol: HTTP
        isTLS: true
EOF
}

# Native FATE is an independent federation. Only Alice needs a local adapter.
prepare_fate_adapter() {
  if ! docker exec "${CONTAINER_NAME}" kubectl get appimage fate2-adapter >/dev/null 2>&1; then
    err "Alice 未注册 FATE 适配器 AppImage fate2-adapter"
    return 1
  fi
  log "Alice 本地 FATE 适配器已就绪；保留 Bob BFIA 与 Kimi 原生路由"
}

# 确保对端 ClusterDomainRoute 正确
ensure_peer_route() {
  # Repair only the requested pair. Never delete or relabel another protocol's route.
  local peer_ctr peer_domain ctr route
  if [[ "${PROTOCOL}" == "fate" ]]; then
    prepare_fate_adapter
    return
  elif [[ "${PROTOCOL}" == "bfia" ]]; then
    peer_ctr="${BOB_CTR}"
    peer_domain="${BOB_DOMAIN}"
  else
    peer_ctr="${KIMI_CTR}"
    peer_domain="${KIMI_DOMAIN}"
  fi
  for ctr in "${CONTAINER_NAME}" "${peer_ctr}"; do
    for route in "alice-${peer_domain}" "${peer_domain}-alice"; do
      docker exec "${ctr}" kubectl delete domainroute "${route}" -A --ignore-not-found >/dev/null 2>&1 || true
      docker exec "${ctr}" kubectl delete clusterdomainroute "${route}" --ignore-not-found >/dev/null 2>&1 || true
    done
  done
  if [[ "${PROTOCOL}" == "bfia" ]]; then
    log "重建 Alice <-> Bob 的 BFIA 路由 ..."
    docker exec "${BOB_CTR}" cat /home/kuscia/var/certs/domain.crt > "/tmp/${BOB_DOMAIN}.domain.crt"
    docker exec "${CONTAINER_NAME}" cat /home/kuscia/var/certs/domain.crt > "/tmp/alice.domain.crt"
    docker cp "/tmp/${BOB_DOMAIN}.domain.crt" "${CONTAINER_NAME}:/home/kuscia/var/certs/${BOB_DOMAIN}.domain.crt" >/dev/null
    docker cp "/tmp/alice.domain.crt" "${BOB_CTR}:/home/kuscia/var/certs/alice.domain.crt" >/dev/null
    rm -f "/tmp/${BOB_DOMAIN}.domain.crt" "/tmp/alice.domain.crt"

    docker exec "${CONTAINER_NAME}" scripts/deploy/add_domain.sh "${BOB_DOMAIN}" "p2p" "bfia" "" >/dev/null
    docker exec "${BOB_CTR}" scripts/deploy/add_domain.sh "alice" "p2p" "bfia" "" >/dev/null

    docker exec "${CONTAINER_NAME}" kubectl patch domain bob --type merge -p '{"spec":{"interConnProtocols":["bfia"]}}' >/dev/null
    docker exec "${BOB_CTR}" kubectl patch domain alice --type merge -p '{"spec":{"interConnProtocols":["bfia"]}}' >/dev/null
    docker exec "${CONTAINER_NAME}" kubectl label namespace bob kuscia.secretflow/interconn-protocols=bfia --overwrite >/dev/null
    docker exec "${BOB_CTR}" kubectl label namespace alice kuscia.secretflow/interconn-protocols=bfia --overwrite >/dev/null

    apply_clusterdomainroute "${CONTAINER_NAME}" "alice" "${BOB_DOMAIN}" "${BOB_IP}" "bfia"
    apply_clusterdomainroute "${CONTAINER_NAME}" "${BOB_DOMAIN}" "alice" "192.168.117.2" "bfia"
    apply_clusterdomainroute "${BOB_CTR}" "alice" "${BOB_DOMAIN}" "${BOB_IP}" "bfia"
    apply_clusterdomainroute "${BOB_CTR}" "${BOB_DOMAIN}" "alice" "192.168.117.2" "bfia"
  else
    log "重建 Alice <-> Kimi 的隐语原生路由 ..."
    docker exec "${KIMI_CTR}" cat /home/kuscia/var/certs/domain.crt > "/tmp/${KIMI_DOMAIN}.domain.crt"
    docker exec "${CONTAINER_NAME}" cat /home/kuscia/var/certs/domain.crt > "/tmp/alice.domain.crt"
    docker cp "/tmp/${KIMI_DOMAIN}.domain.crt" "${CONTAINER_NAME}:/home/kuscia/var/certs/${KIMI_DOMAIN}.domain.crt" >/dev/null
    docker cp "/tmp/alice.domain.crt" "${KIMI_CTR}:/home/kuscia/var/certs/alice.domain.crt" >/dev/null
    rm -f "/tmp/${KIMI_DOMAIN}.domain.crt" "/tmp/alice.domain.crt"

    docker exec "${CONTAINER_NAME}" scripts/deploy/add_domain.sh "${KIMI_DOMAIN}" "p2p" "kuscia" "" >/dev/null
    docker exec "${KIMI_CTR}" scripts/deploy/add_domain.sh "alice" "p2p" "kuscia" "" >/dev/null

    apply_clusterdomainroute "${CONTAINER_NAME}" "alice" "${KIMI_DOMAIN}" "${KIMI_IP}" "kuscia"
    apply_clusterdomainroute "${CONTAINER_NAME}" "${KIMI_DOMAIN}" "alice" "192.168.117.2" "kuscia"
    apply_clusterdomainroute "${KIMI_CTR}" "alice" "${KIMI_DOMAIN}" "${KIMI_IP}" "kuscia"
    apply_clusterdomainroute "${KIMI_CTR}" "${KIMI_DOMAIN}" "alice" "192.168.117.2" "kuscia"
  fi
}

verify_route() {
  local ctr="$1"
  local route="$2"
  local expected="$3"
  local actual
  actual=$(docker exec "${ctr}" kubectl get clusterdomainroute "${route}" -o jsonpath='{.spec.interConnProtocol}')
  if [[ "${actual}" != "${expected}" ]]; then
    err "${ctr} 路由 ${route} 协议为 ${actual:-空}，期望 ${expected}"
    return 1
  fi

  local retry=0
  while [[ "${retry}" -lt 30 ]]; do
    local ready
    ready=$(docker exec "${ctr}" kubectl get clusterdomainroute "${route}" \
      -o jsonpath='{range .status.conditions[?(@.type=="Ready")]}{.status}{end}')
    if [[ "${ready}" == "True" ]]; then
      log "${ctr} 路由 ${route} 已就绪 (${expected})"
      return 0
    fi
    sleep 2
    retry=$((retry + 1))
  done
  err "${ctr} 路由 ${route} 在 60 秒内未就绪"
  return 1
}

verify_target_environment() {
  if [[ "${PROTOCOL}" == "fate" ]]; then
    prepare_fate_adapter
  elif [[ "${PROTOCOL}" == "bfia" ]]; then
    verify_route "${CONTAINER_NAME}" "alice-bob" "bfia"
    verify_route "${BOB_CTR}" "bob-alice" "bfia"
  else
    verify_route "${CONTAINER_NAME}" "alice-kimi" "kuscia"
    verify_route "${KIMI_CTR}" "kimi-alice" "kuscia"
  fi
}

# 重启 Alice SecretPad（如果存在启动脚本）
restart_alice_secretpad() {
  if [[ "${RESTART_PAD:-false}" != "true" ]]; then
    log "保持 Alice SecretPad 运行（RESTART_PAD=false）"
    return 0
  fi

  # Alice 固定使用「隐私计算开放互联平台」前端，协议切换只改变内部协议和功能布局。
  local pad_script="${NEWPROJECT_DIR}/scripts/start_secretpad_alice.sh"
  if [[ ! -x "${pad_script}" ]]; then
    warn "未找到 Alice SecretPad 启动脚本: ${pad_script}"
    return 0
  fi

  # 将内部协议名映射为 SecretPad 期望的 default-protocol 值
  local pad_protocol="secretflow"
  if [[ "${PROTOCOL}" == "bfia" ]]; then
    pad_protocol="bfia"
  elif [[ "${PROTOCOL}" == "fate" ]]; then
    pad_protocol="fate"
  fi

  log "重启 Alice SecretPad（协议: ${pad_protocol}）..."
  # 杀掉旧 Alice SecretPad 进程（BFIA 与上游官方均可能占用 18080/18443/19001）
  pkill -f 'NewProject/secretpad/target/secretpad.jar' 2>/dev/null || true
  pkill -f 'NewProject/secretpad-alice-upstream/target/secretpad.jar' 2>/dev/null || true

  # 等待关键端口完全释放，避免新实例启动失败
  local ports=(18080 18443 19001)
  local port_retry=0
  while [[ "${port_retry}" -lt 30 ]]; do
    local busy=0
    for p in "${ports[@]}"; do
      if lsof -i :"${p}" 2>/dev/null | grep -q LISTEN; then
        busy=1
        break
      fi
    done
    if [[ "${busy}" -eq 0 ]]; then
      break
    fi
    sleep 1
    port_retry=$((port_retry + 1))
  done
  if [[ "${port_retry}" -ge 30 ]]; then
    err "旧 SecretPad 端口未释放，无法启动新实例"
    return 1
  fi

  export SECRETPAD_PROTOCOL_DEFAULT="${pad_protocol}"

  # 后台启动
  nohup bash "${pad_script}" >/dev/null 2>&1 &

  # 等待新实例监听 18080
  local start_retry=0
  while [[ "${start_retry}" -lt 60 ]]; do
    if lsof -i :18080 2>/dev/null | grep -q LISTEN; then
      log "Alice SecretPad 新实例已监听 18080（协议: ${pad_protocol}）"
      return 0
    fi
    sleep 1
    start_retry=$((start_retry + 1))
  done
  err "Alice SecretPad 新实例启动后未监听 18080"
  return 1
}

# ==================== 主流程 ====================
main() {
  log "切换 Alice Kuscia 到 ${PROTOCOL} 协议 ..."

  ensure_alice_config
  start_alice_container
  wait_for_kuscia "${CONTAINER_NAME}"
  wait_for_kuscia_crds "${CONTAINER_NAME}"

  if [[ "${PROTOCOL}" == "bfia" ]]; then
    ensure_container_running "${BOB_CTR}"
    wait_for_kuscia "${BOB_CTR}"
    wait_for_kuscia_crds "${BOB_CTR}"
    register_bfia_appimages "${CONTAINER_NAME}"
    register_bfia_appimages "${BOB_CTR}"
  elif [[ "${PROTOCOL}" == "fate" ]]; then
    prepare_fate_adapter
  else
    ensure_container_running "${KIMI_CTR}"
    wait_for_kuscia "${KIMI_CTR}"
    wait_for_kuscia_crds "${KIMI_CTR}"
    register_secretflow_appimage "${CONTAINER_NAME}"
    register_secretflow_appimage "${KIMI_CTR}"
  fi

  ensure_peer_route
  verify_target_environment

  local ip
  ip=$(get_container_ip "${CONTAINER_NAME}")
  log "Alice Kuscia 切换完成: ${CONTAINER_NAME} (${ip})"

  restart_alice_secretpad
}

main
