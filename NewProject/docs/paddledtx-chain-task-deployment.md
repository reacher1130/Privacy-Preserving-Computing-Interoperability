# 在其他环境部署链桨原生「查询链上任务」

此功能在原生管理台的「任务列表」增加只读 UUID 查询。它从现有 XChain 计算合约读取任务摘要，不导入管理库、不重新发布任务，也不修改链上数据。管理台原有任务仍来自自己的 SQL 表。接口默认拒绝查询，只有既有签名登录、具备任务权限的管理员，才能查看部署时绑定的请求方的任务。

## 准备目标环境

- 先确认目标已有正常运行的链桨原生管理台、管理数据库、XChain 计算合约和执行器。原生 Nginx 的 `/dtx/v1/` 应转发到该管理后端，浏览器从同一来源加载网页和 API。脚本不是首次安装工具。
- 准备两份源码：已配齐 `vendor` 且已应用 `auth`、`upload`、`sdk-log` 补丁的历史 `dtx-manager`，以及已启用真实登录、已应用下载修复的历史 `dtx-fe`。本仓库包含补丁和发布工具，不包含两份完整的历史源码及其私有部署配置。若补丁前检失败，应先对齐基线，不要强行应用，也不要把旧版源码覆盖到运行目录。
- 准备目标环境自己的管理员、已有低权限探测用户及权限为 `0600` 的凭据文件（JSON 字段为 `username` 和 `password`，探针处理登录所需的编码）。只传文件路径，不把凭据写入命令、提交或验收报告。准备一条该环境已完成的双执行器训练 UUID；它必须属于本次绑定的链上请求方。不要复用办公 UUID 或办公身份。
- 确认请求方公钥来自实际发布任务的 requester，且与验收任务的链上 `Requester` 一致。它与管理机构公钥可能不同。脚本将目标公钥文件中的 128 个小写十六进制字符作为 `PPCI_CHAIN_TASK_REQUESTER` 传给候选容器，无需复制私钥或助记词。

在目标机设置下列发布变量。不要沿用办公默认值来部署到其他环境。

| 变量 | 填写内容 |
| --- | --- |
| `PPCI_DTX_MANAGER_CONTAINER` | 当前管理后端容器名。须为既有 scratch 管理后端，使用 `/home/conf`、`/home/log`、`/home/data`、`/home/upload` 绑定目录。 |
| `PPCI_DTX_NATIVE_ROOT` / `PPCI_DTX_UI_CONTAINER` | 原生 UI 源码根目录及当前 Nginx 容器；容器读取该源码根目录下的 `build/`。 |
| `PPCI_DTX_BASE_URL` | 原生管理台的 origin，含协议和端口，不带尾部斜杠或 `/dtx/console/` 路径。它必须能从部署主机访问。 |
| `PPCI_DTX_MANAGER_HOST_PORT` / `PPCI_DTX_MANAGER_CONTAINER_PORT` | 代理连接的宿主端口和管理容器内实际监听端口；与 Nginx `/dtx/v1/` upstream 对齐。 |
| `PPCI_DTX_MANAGER_GATEWAY` | 可选。显式指定前端使用的宿主网关 IPv4；未设置则从原生 UI 容器解析 `host.docker.internal`。 |
| `PPCI_DTX_CHAIN_NETWORK` / `PPCI_DTX_DB_NETWORK` | 当前管理后端使用的计算链、数据库 Docker 网络。 |
| `PPCI_DTX_STATE_ROOT` | 目标管理状态根目录，用于定位该环境的状态与默认凭据路径；配置和业务数据挂载按当前容器核对。 |
| `PPCI_DTX_BUILD_ROOT` / `PPCI_DTX_RELEASE_ROOT` | 已存在的构建与受限发布备份根目录。 |
| `PPCI_DTX_REQUESTER_PUBLIC_KEY_FILE` / `PPCI_DTX_REQUESTER_CONTAINER` | 二选一。前者为部署主机上的公钥文件；未设置时读取后者容器内的 `/home/reqkeys/public.key`。确认与验收任务匹配。 |
| `PPCI_DTX_ADMIN_CREDENTIALS` / `PPCI_DTX_PROBE_CREDENTIALS` | 目标机上既有管理员、低权限探测账号的本地 JSON 文件路径。 |
| `PPCI_DTX_EXPECTED_EXECUTORS` | 验收任务的两个原生执行器名称，用英文逗号分隔；默认 `executor1,executor2`。 |

## 在隔离目录构建

下列命令在 Linux 目标主机执行。预先设置 `REPO_ROOT`（本仓库绝对路径）、`MANAGER_SOURCE`（已准备的后端源码）、`GO_BIN`（Go 1.24）、`NODE_BIN`（Node 20 的 `bin` 目录），以及本机 `CA_BUNDLE` 和 `TZ_FILE` 路径。构建目录中只放源码、依赖和候选产物，不复制运行配置、日志或数据库。

```bash
set -euo pipefail
umask 077
patches="$REPO_ROOT/NewProject/scripts/patches"
BUILD_ROOT="$PPCI_DTX_BUILD_ROOT"
NATIVE_ROOT="$PPCI_DTX_NATIVE_ROOT"
manager_stage=$(mktemp -d "$BUILD_ROOT/.stage-dtx-manager-chain-task.XXXXXXXX")
ui_stage=$(mktemp -d "$BUILD_ROOT/dtx-native-chain-task.XXXXXXXX")
index=static/unicom-dtx/page/index.html

rsync -a --exclude=/.git --exclude=/bin --exclude=/log --exclude=/image \
  --exclude=/conf --exclude=/data --exclude=/upload \
  "$MANAGER_SOURCE/" "$manager_stage/"
cp "$patches/paddledtx-manager-chain-task.patch" "$manager_stage/manager.patch"
(
  cd "$manager_stage"
  if git apply --check manager.patch; then git apply manager.patch
  else git apply --reverse --check manager.patch; fi
  export GOENV=off GOPROXY=off GOTOOLCHAIN=local CGO_ENABLED=0 GOFLAGS=-mod=vendor
  "$GO_BIN" test -p 2 ./pkg/auth ./pkg/filesafe ./controllers \
    -run 'Test(AuthorizationRecoveryBoundary|UploadRecoveryBoundary|RecoveryAuthorityPolicy|ChainTask)' -count=1
  mkdir -p image
  "$GO_BIN" build -p 2 -ldflags='-s -w' -o image/dtx-manager .
  "$GO_BIN" build -p 2 -o check "$REPO_ROOT/NewProject/scripts/check_paddledtx_manager.go"
  cp "$TZ_FILE" image/localtime
  cp "$CA_BUNDLE" image/ca-certificates.crt
  cat > image/Dockerfile <<'DOCKERFILE'
FROM scratch
COPY dtx-manager /home/dtx-manager
COPY localtime /etc/localtime
COPY ca-certificates.crt /etc/ssl/certs/ca-certificates.crt
WORKDIR /home
ENTRYPOINT ["/home/dtx-manager"]
DOCKERFILE
)
candidate_tag="ppci/dtx-manager:chain-task-$(date +%Y%m%d%H%M%S)"
docker build -t "$candidate_tag" "$manager_stage/image"
candidate_image=$(docker image inspect -f '{{.Id}}' "$candidate_tag")

rsync -a --exclude=/.git --exclude=/build --exclude=/node_modules \
  "$NATIVE_ROOT/" "$ui_stage/"
cp "$patches/paddledtx-native-chain-task.patch" "$ui_stage/chain-task.patch"
sha256sum "$NATIVE_ROOT/build/$index" | cut -d' ' -f1 > "$ui_stage/live-index.sha256"
(
  cd "$ui_stage"
  git apply --check chain-task.patch
  git apply chain-task.patch
  export PATH="$NODE_BIN:$PATH" NODE_OPTIONS=--max-old-space-size=3072
  npm ci --ignore-scripts --legacy-peer-deps --prefer-offline --no-audit --fund=false
  node --test scripts/check-download.cjs
  npm run build
  grep -Fq 'window.__DTX_DEMO_AUTH_DISABLED__ = false;' "build/$index"
  sha256sum "build/$index" | cut -d' ' -f1 > candidate-index.sha256
  sha256sum chain-task.patch "build/$index"
)
```

在构建机上固定候选镜像 ID、两个补丁和静态入口的 SHA-256。如果在另一台同架构主机构建，导入镜像及候选后重新核对摘要。不要直接运行办公环境的恢复脚本；它还包含初始化管理库和部署合约的逻辑。准备历史源码时可参照 [管理后台恢复记录](office-manager-recovery-20261102.md) 和 [原生下载构建记录](office-recovery-20261102/native-download.md)。

## 发布、验收与回退

在维护窗口由目标机管理员核对原容器 ID 和运行状态，备份管理库、当前配置与静态入口，再调用 [发布脚本](../scripts/deploy_paddledtx_chain_task.sh)。`validation_task_uuid` 应填目标环境已有的真实训练 UUID，不会触发新计算。前端候选目录须保留 `live-index.sha256` 和 `candidate-index.sha256`；每个文件只有一行 SHA-256，分别对应核对过的线上基线和测试通过的候选入口。当前管理配置须包含 `runSyncdb` 项，发布脚本会在候选配置副本中将它设为 `false`。

```bash
release_script="$REPO_ROOT/NewProject/scripts/deploy_paddledtx_chain_task.sh"
previous_container=$(docker inspect -f '{{.Id}}' "$PPCI_DTX_MANAGER_CONTAINER")
"$release_script" publish "$manager_stage" "$ui_stage" \
  "$previous_container" "$candidate_image" "$validation_task_uuid"
```

发布保留旧容器与旧哈希资源，候选沿用原管理库和链，关闭启动时的 schema 同步。先验收匿名、低权限和无效 UUID 被拒绝、管理员能读同一任务、原管理列表计数不变，再从原生网页实际登录、查询并核对执行器和模型引用。当前 UI 来源文案固定为 `Alice · paddlempc`；目标组织或计算合约名称不同的，应在前端补丁中调整文案后重新构建，不能只改部署参数。

发布异常时，核对旧容器已恢复并可正常登录。需要手动回退，使用相同环境变量和该次脚本输出的发布目录：

```bash
"$release_script" rollback "$release_dir"
```

回退恢复旧管理容器和旧静态入口；不回写数据库、账本或业务文件。备份目录可能含服务配置，仅保留在受限路径，不提交或打包外传。
