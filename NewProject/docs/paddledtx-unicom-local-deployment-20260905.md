# 链桨（PaddleDTX 联通定制）本地部署记录

日期：2026-09-05

这份记录对应 `shared-exchange-Connectivity/PaddleDTX` 的本地可复现部署，使用一条外部 Docker 网络把 XChain、XuperDB dataowner/storage 和两个 DAI executor 连接起来。这里的“链桨协议”指 `PaddleDTX` 的 `paddlempc` 原生合约/DAI 执行链路，不是另起一套 Fabric dtxmanager。

## 已部署的运行时

| 层 | 容器/镜像 | 本机端口 |
| --- | --- | --- |
| XChain | `xchain1/2/3.node.com` · `registry.baidubce.com/paddledtx/xchain:v3.9` | `37201 -> 37101`、`8908 -> 8084`（xchain1） |
| XuperDB dataowner | `dataowner1/2/3.node.com` · `registry.baidubce.com/paddledtx/xdb-dataowner:2.1` | `8441/8442/8443` |
| XuperDB storage | `storage1/2/3.node.com` · `registry.baidubce.com/paddledtx/xdb-storage:2.1` | `38201/38202/38203` |
| DAI executor | `executor1/2.node.com` · `paddledtx-dai:2.1-local-20260905-static-cgo` | `8511/8512`、`38301/38303` |

所有容器加入 Docker 网络 `blockchain_network`。XChain 上部署的是合并后的 `paddlempc` 原生合约（同时覆盖 XDB 文件授权和 DAI 任务方法），而不是把 Fabric shim 的独立 `dtxmanager` 二进制错误地部署到 XChain。

## 启动顺序

在 `shared-exchange-Connectivity/PaddleDTX` 目录执行（首次部署）：

```bash
docker network create blockchain_network 2>/dev/null || true
docker compose -p paddledtx-chain-local -f testdata/blockchain/xchain/docker-compose.yml up -d
docker compose -p paddledtx-xdb-local -f testdata/xdb/docker-compose.yml up -d
docker compose -p paddledtx-executor-local -f testdata/executor/docker-compose.local.yml up -d
```

`docker-compose.local.yml` 现在只启动 `executor1` 和 `executor2`，并挂载各自的 `conf`、`keys`、`ukeys`、`logs`、PaddleFL 目录和 Docker socket；XChain compose 同时加入自身 peer 网络和外部 `blockchain_network`，因此不再需要手动 `docker network connect`。本地镜像需先构建/导入：

```bash
docker build --platform linux/amd64 -f dai/Dockerfile.local -t paddledtx-dai:2.1-local-20260905-static-cgo dai
```

首次启动或清理数据后，需要用 `dai/blockchain/xchain/contract` 的合并合约部署 `paddlempc`，并将三个 dataowner 配置为该合约；随后再启动 storage 和 executor。executor 配置中的 `dtxcontractname`/`managerContractName` 都必须指向 `paddlempc`，`type` 为 `xchain`。

## 验收证据

- `ListExecutorNodes` 查询到 `executor1.node.com:38301`、`executor2.node.com:38303` 且状态为 online。
- `POST http://127.0.0.1:8511/v1/task/list` 和 `8512` 返回 HTTP 200。
- 真实双节点纵向线性回归任务
  `06b7555e-b49e-46c8-bce2-244e47bb74dc`
  从发布、双方文件授权、Ready、启动到 Finished 全流程通过：
  - `StartTime=2026-09-05 20:08:25`
  - `EndTime=2026-09-05 20:08:27`
  - `ErrMessage` 为空
  - 两个 executor 均产生结果文件 ID。

- SecretPad 前端“链桨（PaddleDTX）适配器”再次真实提交任务
  `6a6636a6-9ad7-4fd8-9230-2f622d6b3155`：
  - `linear-vl`，两方文件，PSI `id`，训练目标列 `MEDV`；
  - 页面先 publish，再由后端等待 XChain Confirming→Ready 后执行 `task start`；
  - 页面、requester-cli 链上查询和两个 executor 日志均确认 `Finished`，无 ErrMessage，结果 map 含两份 executor 输出。

该任务是 XChain/XuperDB/两个 DAI executor 的真实 MPC 运行，不是只调用健康检查接口。

## SecretPad 接入约定

SecretPad 的链桨适配器应使用 `paddlempc` 任务协议和本目录中的 requester 配置；不要单独启动 Fabric 版 `dtxmanager` 并把它当成 XChain 合约。requester CLI 配置样例在 `testdata/executor/requester-config.toml`，本地请求端二进制为 `dai/requester-cli-linux-amd64`（linux/amd64，需在对应容器或 amd64 主机运行）。

SecretPad Alice 启动时设置：

```bash
PADDLEDTX_REQUESTER_COMMAND=/abs/path/NewProject/scripts/paddledtx-requester-wrapper.sh \
PADDLEDTX_REQUESTER_CONFIG=/abs/path/shared-exchange-Connectivity/PaddleDTX/testdata/executor/requester-config.toml \
bash NewProject/scripts/start_secretpad_alice.sh
```

wrapper 会把配置参数固定映射到 executor 容器内的 `/home/conf/requester-config.toml`，不会把私钥打印到日志。
