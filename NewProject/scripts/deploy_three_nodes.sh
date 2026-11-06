#!/bin/bash
#
# 三节点 P2P Kuscia 部署脚本（Alice / Bob / Kimi）
#
# 说明:
#   - Alice: 可切换协议（默认隐语原生），固定 IP 192.168.117.2
#   - Bob:   固定 BFIA 协议，使用已有 kuscia-node-bob 目录，固定 IP 192.168.117.3
#   - Kimi:  固定隐语原生协议，固定 IP 192.168.117.4
#
# 用法:
#   ./deploy_three_nodes.sh             # 部署/检查三个节点
#   ./deploy_three_nodes.sh --reset     # 重置并重新部署（会丢失容器 overlay 数据）
#
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
NEWPROJECT_DIR="${PROJECT_DIR}/NewProject"
KUSCIA_DIR="${NEWPROJECT_DIR}/kuscia"

NETWORK_NAME="kuscia-exchange"
KUSCIA_IMAGE="${KUSCIA_IMAGE:-secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/kuscia:1.2.0b0}"
SECRETFLOW_IMAGE="${SECRETFLOW_IMAGE:-secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/secretflow-lite-anolis8:1.11.0b1}"

ALICE_CTR="${USER}-kuscia-autonomy-alice"
BOB_CTR="${USER}-kuscia-autonomy-bob"
KIMI_CTR="${USER}-kuscia-autonomy-kimi"

ALICE_IP="192.168.117.2"
BOB_IP="192.168.117.3"
KIMI_IP="192.168.117.4"

RESET=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --reset) RESET=true; shift ;;
    -h|--help) sed -n '1,20p' "$0"; exit 0 ;;
    *) echo "[ERROR] 未知参数: $1"; exit 1 ;;
  esac
done

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log()  { echo -e "${GREEN}[DEPLOY]${NC} $1"; }
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

# 生成 autonomy 节点配置目录
generate_domain_config() {
  local domain="$1"
  local protocol="$2"
  local work_dir="$3"
  local conf_file="${work_dir}/kuscia.yaml"

  mkdir -p "${work_dir}/images"
  if [[ ! -f "${conf_file}" ]] || [[ -d "${conf_file}" ]]; then
    [[ -d "${conf_file}" ]] && rm -rf "${conf_file}"
    docker run --rm "${KUSCIA_IMAGE}" kuscia init --mode autonomy --domain "${domain}" > "${conf_file}"

    if [[ "${protocol}" == "bfia" ]]; then
      cat >> "${conf_file}" <<EOF
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
                value: transport.${domain}.svc
              - name: system.storage
                value: file:///home/kuscia/var/storage
              - name: system.storage.localfile
                value: file:///home/kuscia/var/storage
            selectors:
              - key: maintainer
                value: secretflow-contact@service.alipay.com
EOF
    else
      cat >> "${conf_file}" <<'EOF'
agent:
  allowPrivileged: true
EOF
    fi
    log "已生成 ${domain} (${protocol}) 配置: ${conf_file}"
  fi
}

# 启动/重启指定 autonomy 容器
ensure_autonomy_container() {
  local domain="$1"
  local protocol="$2"
  local ctr="$3"
  local ip="$4"
  local work_dir="$5"
  local volume_name="${ctr}-containerd"
  local hostname
  hostname=$(echo "${ctr}-$(hostname)" | cut -c 1-63 | tr '[:upper:]_.' '[:lower:]--' | sed 's/^[^a-z0-9]//; s/[^a-z0-9]$//g')

  generate_domain_config "${domain}" "${protocol}" "${work_dir}"

  if docker ps -a --format '{{.Names}}' | grep -q "^${ctr}$"; then
    if [[ "${RESET}" == "true" ]]; then
      warn "重置容器: ${ctr}"
      docker stop "${ctr}" >/dev/null 2>&1 || true
      docker rm "${ctr}" >/dev/null 2>&1 || true
    else
      if docker ps --format '{{.Names}}' | grep -q "^${ctr}$"; then
        log "${domain} 容器已在运行: ${ctr} ($(get_container_ip ${ctr}))"
        return 0
      fi
      log "启动已停止的 ${domain} 容器: ${ctr}"
      docker start "${ctr}" >/dev/null 2>&1
      return 0
    fi
  fi

  ensure_network
  docker volume inspect "${volume_name}" >/dev/null 2>&1 || docker volume create "${volume_name}"

  log "创建 ${domain} (${protocol}) 容器: ${ctr} ..."
  docker run -dit --name="${ctr}" \
    --hostname="${hostname}" \
    --restart=always \
    --network="${NETWORK_NAME}" \
    --ip="${ip}" \
    --privileged \
    -v "${volume_name}:/home/kuscia/containerd" \
    -v "${work_dir}/kuscia.yaml:/home/kuscia/etc/conf/kuscia.yaml" \
    -v "${work_dir}/images:/home/kuscia/var/images" \
    "${KUSCIA_IMAGE}" bin/kuscia start -c etc/conf/kuscia.yaml
}

# 等待容器 K3s 就绪
wait_for_k3s() {
  local ctr="$1"
  log "等待 ${ctr} K3s 就绪 ..."
  local retry=0
  while [[ "${retry}" -lt 60 ]]; do
    local code
    code=$(docker exec "${ctr}" curl -sk -o /dev/null -w '%{http_code}' https://127.0.0.1:6443 2>/dev/null | tr -d '\r\n' || echo "000")
    if [[ "${code}" == "200" || "${code}" == "401" || "${code}" == "403" ]]; then
      log "${ctr} K3s 已就绪"
      return 0
    fi
    sleep 2
    retry=$((retry + 1))
  done
  warn "${ctr} K3s 启动超时"
  return 1
}

# 等待 Kuscia CRD 就绪
wait_for_kuscia_crds() {
  local ctr="$1"
  log "等待 ${ctr} Kuscia CRD 就绪 ..."
  local retry=0
  while [[ "${retry}" -lt 60 ]]; do
    if docker exec "${ctr}" kubectl get crd appimages.kuscia.secretflow >/dev/null 2>&1; then
      log "${ctr} Kuscia CRD 已就绪"
      return 0
    fi
    sleep 2
    retry=$((retry + 1))
  done
  warn "${ctr} Kuscia CRD 等待超时"
  return 1
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
  docker exec "${ctr}" mkdir -p /home/kuscia/scripts/user/bfia
  for yaml in "${bfia_yaml_dir}"/ic-*.yaml; do
    [[ -f "${yaml}" ]] || continue
    local name app_image
    name=$(basename "${yaml}")
    app_image=$(awk '/^  name:/{print $2; exit}' "${yaml}")
    docker cp "${yaml}" "${ctr}:/home/kuscia/scripts/user/bfia/${name}" >/dev/null
    docker exec "${ctr}" kubectl apply -f "/home/kuscia/scripts/user/bfia/${name}" >/dev/null
    docker exec "${ctr}" kubectl get appimage "${app_image}" >/dev/null
  done
}

# 建立两个 autonomy 节点间的互联（BFIA 或 kuscia 协议）
build_interconn() {
  local host_ctr="$1"
  local member_ctr="$2"
  local member_domain="$3"
  local host_domain="$4"
  local interconn_protocol="$5"
  local host_ip member_ip
  host_ip=$(get_container_ip "${host_ctr}")
  member_ip=$(get_container_ip "${member_ctr}")

  log "建立 ${member_domain} <-> ${host_domain} (${interconn_protocol}) 互联 ..."

  # 交换 domain.crt
  docker exec "${member_ctr}" cat /home/kuscia/var/certs/domain.crt > "/tmp/${member_domain}.domain.crt" 2>/dev/null || {
    err "无法获取 ${member_domain} domain.crt"
    return 1
  }
  docker exec "${host_ctr}" cat /home/kuscia/var/certs/domain.crt > "/tmp/${host_domain}.domain.crt" 2>/dev/null || {
    err "无法获取 ${host_domain} domain.crt"
    rm -f "/tmp/${member_domain}.domain.crt"
    return 1
  }
  docker cp "/tmp/${member_domain}.domain.crt" "${host_ctr}:/home/kuscia/var/certs/${member_domain}.domain.crt" >/dev/null
  docker cp "/tmp/${host_domain}.domain.crt" "${member_ctr}:/home/kuscia/var/certs/${host_domain}.domain.crt" >/dev/null
  rm -f "/tmp/${member_domain}.domain.crt" "/tmp/${host_domain}.domain.crt"

  # 在两侧注册对端 Domain；Domain 控制器会自动创建入向/出向 ClusterDomainRoute
  docker exec "${host_ctr}" scripts/deploy/add_domain.sh "${member_domain}" "p2p" "${interconn_protocol}" "" >/dev/null
  docker exec "${member_ctr}" scripts/deploy/add_domain.sh "${host_domain}" "p2p" "${interconn_protocol}" "" >/dev/null

  # 为自动创建的 ClusterDomainRoute 补充 endpoint（对端 IP），
  # 控制器随后会同步出包含 TokenConfig 公钥的 DomainRoute。
  apply_clusterdomainroute "${host_ctr}" "${member_domain}" "${host_domain}" "${member_ip}" "${interconn_protocol}"
  apply_clusterdomainroute "${host_ctr}" "${host_domain}" "${member_domain}" "${member_ip}" "${interconn_protocol}"
  apply_clusterdomainroute "${member_ctr}" "${host_domain}" "${member_domain}" "${host_ip}" "${interconn_protocol}"
  apply_clusterdomainroute "${member_ctr}" "${member_domain}" "${host_domain}" "${host_ip}" "${interconn_protocol}"

  local host_route_protocol member_route_protocol
  host_route_protocol=$(docker exec "${host_ctr}" kubectl get clusterdomainroute "${host_domain}-${member_domain}" -o jsonpath='{.spec.interConnProtocol}')
  member_route_protocol=$(docker exec "${member_ctr}" kubectl get clusterdomainroute "${member_domain}-${host_domain}" -o jsonpath='{.spec.interConnProtocol}')
  [[ "${host_route_protocol}" == "${interconn_protocol}" ]]
  [[ "${member_route_protocol}" == "${interconn_protocol}" ]]
  wait_for_route_ready "${host_ctr}" "${host_domain}-${member_domain}"
  wait_for_route_ready "${member_ctr}" "${member_domain}-${host_domain}"
}

wait_for_route_ready() {
  local ctr="$1"
  local route="$2"
  local retry=0
  while [[ "${retry}" -lt 30 ]]; do
    local ready
    ready=$(docker exec "${ctr}" kubectl get clusterdomainroute "${route}" \
      -o jsonpath='{range .status.conditions[?(@.type=="Ready")]}{.status}{end}')
    if [[ "${ready}" == "True" ]]; then
      log "${ctr} 路由 ${route} 已就绪"
      return 0
    fi
    sleep 2
    retry=$((retry + 1))
  done
  err "${ctr} 路由 ${route} 在 60 秒内未就绪"
  return 1
}

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

# 显示状态
show_status() {
  echo ""
  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}  三节点 Kuscia 状态${NC}"
  echo -e "${GREEN}========================================${NC}"
  for ctr in "${ALICE_CTR}" "${BOB_CTR}" "${KIMI_CTR}"; do
    local status ip
    if docker ps --format '{{.Names}}' | grep -q "^${ctr}$"; then
      status="${GREEN}Running${NC}"
    elif docker ps -a --format '{{.Names}}' | grep -q "^${ctr}$"; then
      status="${YELLOW}Stopped${NC}"
    else
      status="${RED}Not Found${NC}"
    fi
    ip=$(get_container_ip "${ctr}")
    echo -e "  ${ctr}: ${status}  IP: ${ip:-N/A}"
  done
  echo -e "${GREEN}========================================${NC}"
}

# ==================== 主流程 ====================
main() {
  log "开始部署三节点 Kuscia ..."

  ensure_network

  # Alice: 可切换，默认原生
  ensure_autonomy_container "alice" "kuscia" "${ALICE_CTR}" "${ALICE_IP}" "${PROJECT_DIR}/${ALICE_CTR}"
  wait_for_k3s "${ALICE_CTR}"
  wait_for_kuscia_crds "${ALICE_CTR}"
  register_secretflow_appimage "${ALICE_CTR}"
  # 同时预注册 BFIA AppImage，便于前端切换到 BFIA 后直接使用
  register_bfia_appimages "${ALICE_CTR}"

  # Bob: 固定 BFIA，复用现有 kuscia-node-bob 目录
  ensure_autonomy_container "bob" "bfia" "${BOB_CTR}" "${BOB_IP}" "${PROJECT_DIR}/kuscia-node-bob"
  wait_for_k3s "${BOB_CTR}"
  wait_for_kuscia_crds "${BOB_CTR}"
  register_bfia_appimages "${BOB_CTR}"

  # Kimi: 固定隐语原生
  ensure_autonomy_container "kimi" "kuscia" "${KIMI_CTR}" "${KIMI_IP}" "${PROJECT_DIR}/${KIMI_CTR}"
  wait_for_k3s "${KIMI_CTR}"
  wait_for_kuscia_crds "${KIMI_CTR}"
  register_secretflow_appimage "${KIMI_CTR}"

  # 建立路由（build_interconn 会在两侧各创建一条 DomainRoute）
  build_interconn "${ALICE_CTR}" "${BOB_CTR}" "bob" "alice" "bfia"
  build_interconn "${ALICE_CTR}" "${KIMI_CTR}" "kimi" "alice" "kuscia"

  show_status
  log "三节点部署完成"
}

main
