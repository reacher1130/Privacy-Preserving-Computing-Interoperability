# 演示免登录与 BFIA Kuscia 瘦身部署记录

日期：2026-09-06

## 结论

本地演示默认不需要登录。Alice、Bob、Kimi 的 SecretPad 后端默认关闭认证，前端演示构建跳过登录 wrapper；协议入口仍由后端协议配置驱动，当前支持：

| 页面入口 | 后端协议 | 执行引擎 |
| --- | --- | --- |
| 隐语原生 | `secretflow` | SecretFlow / Kuscia |
| BFIA | `bfia` | BFIA interconnect adapter / Kuscia |
| FATE | `fate` | FATE-Flow / `fate2-adapter` |
| 链桨 | `paddledtx` | PaddleDTX / `paddlempc` |

页面切换会同步更新 active protocol 和对应的组件/管理页面，不是只切换菜单文案。

## 免登录开关

演示默认值：

```bash
SECRETPAD_AUTH_ENABLED=false
SECRET_PAD_DEMO_AUTH_DISABLED=true
```

后端脚本和配置已经把 `SECRETPAD_AUTH_ENABLED` 作为显式生产开关；需要恢复鉴权时设置 `SECRETPAD_AUTH_ENABLED=true` 并重新启动后端。前端正常构建默认保留登录，演示构建使用：

```bash
cd NewProject/secretpad-frontend
pnpm --filter secretpad build:demo
```

演示路由使用 `ownerId`/`nodeId` 作为当前节点兜底，例如：

```text
http://127.0.0.1:18100/edge?ownerId=alice&tab=workbench
http://127.0.0.1:18101/edge?ownerId=alice&tab=workbench
http://127.0.0.1:28101/edge?ownerId=bob&tab=workbench
http://127.0.0.1:38101/edge?ownerId=kimi&tab=workbench
```

不要把该配置用于生产环境；免登录只改变演示访问门槛，不代表生产访问控制验收通过。

## 直接测试顺序

1. 打开 Alice 页面，进入“开放互联平台”，确认左侧协议选择器显示“隐语原生 / BFIA / FATE / 链桨”。选择协议后等待页面跳到对应菜单：隐语原生和 BFIA 进入工作台，FATE 进入 `fate-management`，链桨进入 `paddledtx-management`。
2. BFIA：Alice 和 Bob 页面分别上传 `NewProject/testdata/bfia-ui/alice.csv`、`bob.csv`，用 `id` 作为求交键；创建项目并邀请 Bob，Bob 点击同意；创建流程，拖入两个 `datatable` 和 `ecdh-psi`（也可拖入 `ss-lr`），连边、保存/提交，Bob 再同意，Alice 执行并在结果节点查看/下载 CSV。
3. FATE：切换 FATE，在 FATE 管理页登记 Flow/数据集，画布选择 `psi` 或 `coordinated_lr`，绑定 guest/host 后提交；状态应从 READY 到 FINISHED，作业状态为 SUCCESS。
4. 链桨：切换链桨，在管理页选择 `linear-vl`、双方文件、`id` 求交键和两个 executor，点击“发布并执行”；页面轮询到 `Finished` 后查看两 executor 结果。
5. 隐语原生：切回隐语原生，在 Alice/Kimi 两端新建原生项目，拖入原生 `datatable`/PSI 算子，审批后执行；三个节点状态应为 `SUCCEED`。

页面操作不需要输入账号密码；如果要核对后端当前协议，可执行：

```bash
curl -s http://127.0.0.1:18080/api/v1alpha1/config/protocol
```

## BFIA 算子瘦身

BFIA 的 `ss-lr`、`ss-compare`、`ss-pearson`、`ss-vif`、`ss-xgb` 共用一个去除 Python 运行时的 C++ slim 镜像：

- 入口改为镜像内已有的 Bash，保留 `config.*` 和 `system.*` 这类带点环境变量；使用 `/bin/sh`（dash）会丢失这些变量，导致 BFIA 错误回退到 `127.0.0.1:9531`。
- 基础镜像仅保留 `debian:bookworm-slim`、`ca-certificates`、`curl`、`libgomp1` 和剥离符号的 `ic_main`。
- 本地镜像 `ecdh`、`ecdh-psi` 和 `secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/ss-*:latest` 统一使用 digest `sha256:27c3b8a65b61ed526e3f25e101d67aca3f3c95194bf9d055d783f093359f6bfa`，运行时大小约 185 MB（Docker 本地 181,111,900 bytes）。
- 对比旧的 Python slim 镜像约 260 MB，单算子镜像下降约 30%；官方 `morse-ecdh-header:20251113` 仍约 1.82 GB，本次没有把它误称为已瘦身。

构建五个算子：

```bash
cd NewProject/secretflow/interconnection-impl
DOCKER_PLATFORM=linux/amd64 ./docker/build-all.sh
```

## 导入 Alice/Bob Kuscia 内置 K3s

导入脚本会把 AppImage 和算法镜像加载到两个本地 Kuscia 容器的 containerd：

```bash
cd NewProject/secretflow/interconnection-impl
./prepare_all_images.sh --force \
  -a gaofeng-kuscia-autonomy-alice \
  -b gaofeng-kuscia-autonomy-bob
```

已验证：

- Alice 和 Bob K3s 节点均 `Ready`。
- 五个 `ss-*` 算子在两个节点均已导入，digest 一致，CRI 显示约 185 MB。
- Kuscia BFIA controller 为每个任务注入 `system.transport`、文件存储和 `config.node_ip.*`；因此黑盒 BFIA 任务使用 `interconn-scheduler.<domain>.svc` 建链，而不是白盒回退地址。
- 控制器单测：

  ```bash
  cd NewProject/kuscia
  go test ./pkg/interconn/bfia/controller
  ```

## 前端真实 BFIA 验收

通过 Alice 页面创建并配置项目 `bfia-ui-20260905-1618` 中的流程 `ss-lr-slim-e2e-20260906`，页面实际拖拽 `ss-lr` 和两个 `datatable`，配置 Alice 的 10 个特征及 `y` 标签，提交后在 Bob 页面点击“同意”，再回 Alice 点击“执行”。

本次最新作业：

- DAG：`ultccyfx`
- Job：`bpzl`
- 节点状态：三个节点均 `SUCCEED`，进度 `100%`
- Alice 模型结果：`bpzl-host-0/bpzl-998dcefd8e83-result`
- 结果管理页显示结果记录 `4b0cf33be663442fb12b11b8b692a587`
- 页面结果下载请求返回 `text/csv`，内容为 20 行结果

验证不只依赖接口：已在 Alice、Bob 页面完成协议/项目/审批/执行点击，并在 Alice 的“结果管理”页面看到最新记录并点击“下载”。

## 常用检查

```bash
# 后端协议配置（免 token）
curl -s http://127.0.0.1:18080/api/v1alpha1/config/protocol

# K3s 节点
docker exec gaofeng-kuscia-autonomy-alice /home/kuscia/bin/kubectl get nodes
docker exec gaofeng-kuscia-autonomy-bob /home/kuscia/bin/kubectl get nodes

# BFIA 镜像
docker exec gaofeng-kuscia-autonomy-alice /home/kuscia/bin/crictl images | grep 'ss-'
```
