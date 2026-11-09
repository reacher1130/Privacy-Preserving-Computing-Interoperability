# 四协议免登录与运行态验收记录（2026-09-06）

## 结论边界

本记录针对本地演示环境，不代表生产鉴权或生产部署验收。Alice、Bob、Kimi 后端启动参数均为 `--secretpad.auth.enabled=false`，前端使用 `build:demo`；本轮对关键接口均未携带 `User-Token`，返回成功。生产环境应显式设置 `SECRETPAD_AUTH_ENABLED=true` 并使用普通前端构建。

## 协议切换

Alice 的 `POST /api/v1alpha1/node/kuscia/restart` 已按顺序实际切换并验证 `paddledtx`、`secretflow`、`bfia`、`fate`；本轮又在修正双向路由后重复验证了 BFIA、隐语原生、FATE、链桨四次切换。每次返回的 `activeProtocol` 与请求一致，最后恢复 `secretflow` 作为演示默认态。当前配置为：

| 协议 | 引擎/适配器 | 对端 |
| --- | --- | --- |
| `secretflow` | SecretFlow / Kuscia | Alice ↔ Kimi |
| `bfia` | BFIA interconnect adapter / Kuscia | Alice ↔ Bob |
| `fate` | FATE-Flow / `fate2-adapter` | Alice ↔ Bob |
| `paddledtx` | PaddleDTX / `paddlempc` | XChain + executor1/executor2 |

无令牌读取 `GET /api/v1alpha1/config/protocol` 返回四项 `supportedProtocols` 和上述引擎映射。本轮最后读取到 `activeProtocol=secretflow`、`canSwitch=true`。
演示切换入口在 Alice；Bob 固定作为 BFIA 对端、Kimi 固定作为隐语原生对端，因此两者不提供本地协议切换 selector，但三节点页面和后端都走免登录演示上下文。

## 已跑通的真实任务

- 隐语原生：项目 `gzbnqqso`、画布 `thrxhlxi`，任务 `tnka`；Alice/Kimi 两方各 6 行输入，PSI 输出 4 行交集，三个图节点均 `SUCCEED`，无令牌图节点状态 `finished=true`，结果可读取。
- BFIA：历史真实 UI 作业 `bpzl`/DAG `ultccyfx` 已在 Alice/Bob Kuscia 上 `SUCCEED`，结果页显示并下载 20 行模型结果；本轮又用正式重编译并新导入的 C++ slim `ecdh-psi` AppImage 跑通 `wlmf`/DAG `hdzwabpk`，Alice/Bob 两端节点均 `SUCCEED`，双方各 6 行输入生成 5 行 CSV（含表头，即 4 行交集）；BFIA 无令牌组件列表可读。
- BFIA 上传闭环：通过无令牌 `POST /api/v1bfia/dataset/upload` 上传 Alice/Bob CSV，再通过页面同一套 create/metadata、项目/流程审批和画布执行链路提交 `ecdh-psi`。项目 `5570643997524d91b93997d7fd09966f`、流程 `iqdcehaj`、作业 `vyhd` 的 3 个节点均 `SUCCEED`；结果接口返回 `id/age/income` 四行交集，且上传文件已同步到两端 Kuscia `/home/kuscia/var/storage/data/`，证明不是预置文件假成功。
- BFIA 路由回归：修正切换脚本后再次切到 `bfia`，Alice→Bob 与 Bob→Alice 的目标地址分别为对端 Kuscia IP，主任务 `iqdcehaj` 仍为 3/3 `SUCCEED`，作业 `voft` 的输出仍为 `id/age/income` 四行交集。
- FATE：集群 `fc-4ed3f690c2cc409f`（FATE 2.2.0）保持 `ACTIVE`；作业 `fj-276dce85b0274aa8` 为 `SUCCESS`，guest/host 的 `fate2-adapter` 已完成 READY→FINISHED。
- 链桨：无令牌 `GET /api/v1alpha1/paddledtx/status` 返回 `engine=paddlempc`、`requesterConfigured=true`、`ready=true`；在新镜像重建两个 executor 后提交任务 `bdfb8f3c-90b2-472a-aecb-df5b8f3388c9`（`linear-vl`），链上 `Finished`。本轮读取复核任务 `be2c50da-e5b7-408d-ae72-18219b7d4bfa` 为 `exitCode=0`、`Status: Finished`、`ErrMessage` 为空。

链桨当前是 SecretPad 调用 executor 容器内 requester CLI，再由 XChain/paddlempc 协调两 executor；它不是 Kuscia AppImage 调度任务。演示健康门禁通过显式 `PADDLEDTX_DEMO_SKIP_HEALTH=true` 跳过历史七天心跳检查，在线检查仍保留，生产不要设置该变量。

## BFIA 瘦身与 K3s 导入

五个 C++ SS 算子 `ss-lr`、`ss-compare`、`ss-pearson`、`ss-vif`、`ss-xgb` 以及 ECDH 共用 `debian:bookworm-slim + libgomp1 + curl + stripped ic_main` 运行时，不再携带 Python/Bazel/requests。当前 CRI 实际大小约 185MB；本轮全部镜像统一使用 `27c3b8a65b61e`（本地 manifest `sha256:27c3b8a65b61ed526e3f25e101d67aca3f3c95194bf9d055d783f093359f6bfa`）：

```text
ecdh / ecdh-psi / ss-lr / ss-compare / ss-pearson / ss-vif / ss-xgb: 27c3b8a65b61e
```

相比旧 Python slim 约 260MB、官方 `morse-ecdh-header:20251113` 约 1.82GB，当前版本已明显缩小，同时保留 glibc/OpenMP 兼容性。slim 入口显式使用 Bash，避免 Kuscia 以 `/bin/sh` 包装时丢失点号环境变量；入口还把 UI 的 `field_names=id` 规范化为双方字段 JSON。导入命令可重复执行：

```bash
cd NewProject/secretflow/interconnection-impl
./prepare_all_images.sh --force \
  -a gaofeng-kuscia-autonomy-alice \
  -b gaofeng-kuscia-autonomy-bob
```

本轮脚本再次报告 `6 个算法就绪，0 个缺失镜像`；Alice/Bob K3s 的 `kubectl get nodes` 均为 `Ready`，七个 BFIA AppImage（`ic-ecdh`、`ic-ecdh-psi`、五个 `ic-ss-*`）均已注册，两个节点 CRI 均能看到同一 SS digest。BFIA controller 已为黑盒任务注入 `system.transport`、文件存储和 `config.node_ip.*`，避免回退到 `127.0.0.1`。

当前 BFIA 组件树仍按正式目录展示 `ecdh-psi`、`datatable`、`secureboot`、`ss-lr` 四项；`ss-compare`、`ss-pearson`、`ss-vif`、`ss-xgb` 的 AppImage 已导入且转换器已登记，但本轮没有把它们冒充成已完成的逐项端到端验收。

PaddleDTX 两节点 executor compose 已固化为 `paddledtx-dai:2.1-local-20260906-demo`；镜像内直接包含 `/home/requester-cli-demo`，不再依赖手工复制。其外部 XChain 共识层保留 `xchain1/2/3` 三节点，重启后通过各节点内置 `xchain-cli status` 复核三节点均发现彼此；本次读取时三节点同为 `trunkHeight=12412`、同为 `tipBlockid=d5bddcb6cb0d63de61774d38ccdf6dba42bef9f285c6e0d0d9e861e600a5c638`（高度会继续增长）。

## 页面证据与限制

三个本地前端端口 `18101/28101/38101` 的 `/`、`/edge`、`/connectivity-dag`、`/fate-management`、`/paddledtx-management` 在无登录时均返回 HTTP 200 且无 `Location` 重定向。真实页面操作记录包括：BFIA 数据刷新、详情、下载、授权/公开/历史抽屉、合作节点表单、项目画布执行；隐语原生数据源/数据管理/合作节点/项目/结果页面及表单；FATE 集群、作业、数据集、模型、画布控件；链桨发布并执行。删除和最终权限确认只打开后取消，避免演示数据被破坏。Tabbit 运行时不可用；Mac 锁屏后未继续新增点击，故不把 HTTP 路由检查冒充鼠标证据。未列出的算法参数组合和生产部署仍需单独验收。
