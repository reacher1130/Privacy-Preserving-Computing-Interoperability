# 资源盘点（2026-09-07 14:20–14:32，本机实时采样）

## 数量口径

- 平台登记节点：Alice、Bob、Kimi，共 3 个。
- 按实际计算参与实例计：上述 3 个，加 FATE Guest/Host 2 个、PaddleDTX executor 2 个，共 7 个；FATE Arbiter 与 Host 同容器。PaddleDTX 另有 3 个 XChain、3 个 dataowner、3 个 storage 基础设施节点。
- 逻辑平台部署：Alice 开放互联平台、Bob BFIA 对端、Kimi 原生隐语对端、独立 FATE、独立 PaddleDTX，共 5 个。开放互联控制平台本身是 1 个。
- 28 个运行项目 Docker 容器：Kuscia 3 + 代理 5 + PaddleDTX 服务 11 + FATE Guest/Host/Fateboard 3 + Nginx 页面 5 + 旧 FATE 单实例 1。Kuscia 内部任务 Pod 不重复计入 Docker 数量。
- 全机 Docker：33 个容器，32 个运行；比项目多 4 个其他项目运行容器和 1 个已停止旧构建器。

## 内存快照

Docker stats：Kuscia 约 2.77 GiB，FATE Guest/Host/Fateboard 约 2.08 GiB，PaddleDTX 约 3.61 GiB，其余代理、页面及旧 FATE 约 0.08 GiB，共约 8.53 GiB。

vmmap physical footprint：Alice 827.0 MiB、Bob 852.9 MiB、Kimi 850.9 MiB，合计 2.47 GiB。应用口径合计约 11 GiB；这不是整个 OrbStack 虚拟机物理驻留量，容器与宿主统计口径不同，亦未包括虚拟机管理开销和任务峰值。

主机物理内存 24 GiB；系统交换空间已用 13.06 GiB。Java 的 RSS 因内存压缩/交换明显低于 footprint，不能用 RSS 代替完整占用。

## 磁盘

| 范围 | 占用 |
|---|---:|
| 项目目录（du） | 15.41 GiB |
| 28 个项目容器可写层（inspect --size） | 8.26 GiB |
| Alice/Bob/Kimi containerd 卷 | 12.76 GiB |
| 当前 Docker 容器引用的 7 个去重镜像 ID，逻辑大小 | 6.02 GiB |
| 已停止旧 Kuscia 构建器缓存卷 | 6.51 GiB |

前三项合计约 36.43 GiB；含当前基础镜像的运行相关条目约 42.45 GiB，另有旧构建缓存和历史镜像。镜像含共享层，文件系统亦可能压缩或共享块，不能把这里的逻辑合计理解为可精确释放的物理空间。

全机 Docker system df：镜像 53.69 GB，标记可回收 42.7 GB；容器可写层 8.864 GB；卷 20.76 GB；构建缓存 4.446 GB，其中可回收 2.436 GB。全机统计包括其他项目，缓存与镜像口径也可能重叠，不应盲目相加或全部删除。尤其新 FATE 适配器和 BFIA 算子镜像通过嵌套 containerd 使用，外层 Docker 的 CONTAINERS=0 不表示业务无用。

## 可清理候选与代价

1. 已停止约五周的 buildx_buildkit_kuscia0 及其 6.51 GiB 缓存卷：确认退役后删除，不影响当前运行容器；之后重建镜像会失去缓存。
2. .codegraph 约 0.80 GiB：不需要本地代码索引时可删除，未来使用需重新索引。
3. secretpad-frontend/.pnpm-store 约 1.12 GiB：可重建的下载缓存；再次安装需要下载。硬链接使实际释放可能小于 du 数字。
4. secretflow/interconnection-impl/.cache 约 6.64 GiB：编译/依赖缓存，有持续开发价值，建议后于旧构建器清理；删除后 C++ 编译可能重新下载和构建依赖。
5. 18100 的旧前端容器 secretpad-frontend-e2e：已由 18101 统一入口覆盖，可退役；约 4.75 MiB 内存，几乎不释放共享镜像空间。旧 fate2-flow-e2e（19380）可列为退役候选，但须先核对 Fateboard 连接并备份其约 0.51 GiB 可写层数据。
6. 18103/38103/18511 原生参考界面不是当前统一入口必需，可按是否需要对照页面停用，节省的内存很少；不删除对应计算后端。
7. 无标签旧试验镜像须逐个核对构建用途与回滚需求；42.7 GB 全机未引用镜像中大量属于 Wanwu/AskXuan/订阅项目，不属于本项目清理范围。

必须保留：现用数据卷、账本、FATE 数据和模型、节点证书、已部署站点目录、当前镜像和源码。备份在确认恢复能力前保留。本轮仅盘点，未删除资源。
