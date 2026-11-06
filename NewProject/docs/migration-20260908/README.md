# Linux AMD64 迁移与部署记录

目标：`192.168.45.101`，SSH 端口 `2222`。系统为 Anolis OS 8.10，16 核、约 32 GB 内存。现有其他业务保留，未重启服务器或 Docker 守护进程。

## 已部署拓扑与入口

本项目共 **28 个常驻 Docker 容器和 3 个 systemd Java 后端**。不采用按需启动。

| 平台入口 | 地址 | 协议范围 |
| --- | --- | --- |
| Alice 统一平台 | http://192.168.45.101:18101/edge?tab=workbench | 原生隐语、BFIA、FATE、PaddleDTX |
| Bob 平台 | http://192.168.45.101:28101/edge?tab=workbench | 仅 BFIA |
| Kimi 平台 | http://192.168.45.101:38101/edge?tab=workbench | 原生隐语 |
| Alice 原生隐语页面 | http://192.168.45.101:18103/ | 节点工作台 |
| Kimi 原生隐语页面 | http://192.168.45.101:38103/ | 节点工作台 |
| FATEBoard | http://192.168.45.101:19383/ | 独立 FATE 平台页面 |
| PaddleDTX 原生页面 | http://192.168.45.101:18511/ | 保留现有原生前端 |

FATE Guest/Host 独立部署，不放入 Bob。FATEBoard 保留自身的参考 Flow；它与 Guest/Host 的原生任务记录是不同实例，页面可访问不代表其列表包含 Guest/Host 任务。

## 首轮真实任务验收

下表为首轮迁移记录；服务器源码重建后的新一轮验收和本地清理情况见 [服务器开发与运维](REMOTE-DEVELOPMENT.md)。

| 协议 | 新任务 | 结果 |
| --- | --- | --- |
| BFIA，Alice/Bob | `ltlh` | 输入与 PSI 共三个节点均 `SUCCEED` |
| 原生隐语，Alice/Kimi | `qalb` | 输入与 PSI 共三个节点均 `SUCCEED` |
| PaddleDTX | `9ac8acc5-7abb-4b86-8b1e-e01c28c17549` | 使用保留的数据集及模型完成预测，`Finished` |
| FATE | 平台 `fj-129373369bbd4ace`；原生 `202609080928321586790` | 平台 `SUCCESS`；Guest、Host、Arbiter 任务均成功，包含 PSI 和两轮联合逻辑回归 |

验收文件位于本目录。已单独读取 FATE 两端原生任务与子任务，结果见 `fate-native-*.json`。首轮 FATE 失败源于 Linux 上回环端口无法由嵌套容器访问；已增加 Docker 内部网关绑定并重试成功，首轮记录保存在 `fate-first-*.json`。

已停止并重新启动本项目全部 28 个容器及三个后端，整体健康检查通过；未重启整台服务器。项目、画布、数据表和任务数量与源数据库核对未减少，新增验收任务已持久保存。BFIA 的 H2 项目通过专用 API 和真实浏览器项目页另行核对。

浏览器已检查 Alice 历史项目、BFIA 项目和流程列表、Kimi 原生节点工作台、FATEBoard 的 RUNNING/JOBS 导航及 PaddleDTX 原生控制台。原生隐语根路径已重定向至 `/edge?tab=workbench`，避免进入 Center 页面。PaddleDTX 根路径指向源码配置的 `/dtx/console/`；重定向保留宿主机映射端口，解决根目录 403 和错误静态文件入口的空白页。

## 运维

登录服务器后运行：

```bash
ppci-platform status
ppci-platform stop
ppci-platform start
ppci-platform restart
```

这些命令只操作迁移清单内的本项目服务。三个后端服务名是 `ppci-alice`、`ppci-bob`、`ppci-kimi`，均已设置开机启动；28 个容器采用 `unless-stopped`。人工执行 stop 后会保持停止，重新 start 后恢复常驻运行。

```bash
systemctl status ppci-alice ppci-bob ppci-kimi
tail -f /var/log/ppci/alice/bootstrap.log
docker logs --tail 100 gaofeng-kuscia-autonomy-alice
```

项目使用独立的 JDK 21 和 Python 3.11。服务器原有 Java 11 默认值、系统 Python 和 Docker 代理配置均保留。维护脚本请使用 `python3.11`。

## 文件与备份

- 程序、源码、发布产物：`/opt/ppci`。
- 三个平台数据库仍保留在各自项目目录；Bob 的外部 SQLite/Quartz 数据已从 Mac `/tmp/secretpad-bob-runtime` 迁入 `/srv/ppci/secretpad-bob-runtime`。
- Kuscia 持久业务状态：`/srv/ppci/kuscia/{alice,bob,kimi}/root/home/kuscia/var`，包含原身份、证书、集群数据库和业务存储。
- Java 日志：`/var/log/ppci/{alice,bob,kimi}`。
- 迁移备份：`/var/backups/ppci/migration-20260908`。包括 18 个有状态容器的完整文件系统归档、SHA256、容器及网络清单、源数据库和配置归档、算法镜像及目标原有服务配置。
- Bob 外部数据库的迁移前副本：备份目录内 `host-state/secretpad-bob-runtime`。

ARM64 的 Kuscia、Nginx、socat、原生隐语运行镜像已替换为 AMD64。Kuscia 使用当前修改后的源码在服务器重新编译；七个 BFIA 算法及 FATE 适配器保留已验收的 AMD64 镜像。FATE、链和存储容器通过完整文件系统归档恢复，再用 inspect 清单重建配置，保留容器内的数据和修复。

Kuscia 的 containerd 运行缓存在目标端按 AMD64 重建，原 ARM64 卷随后已从 Mac 清理，没有混入目标运行环境。依赖目录中的自定义补丁和覆盖源码已补齐；BFIA 后续迁移还传输了 Linux Bazel、下载归档和外部源码缓存，在服务器重新生成编译对象。node_modules、pnpm store 和 Codegraph 索引未作为运行依赖迁移。

迁移网络使用 `ppci-` 前缀，保留 Kuscia `192.168.117.0/24`、链数据 `192.168.107.0/24` 等必要地址；通用服务网络调整为 `10.240.0.0/24`，避免与服务器原网段重叠。FATE Guest/Host 同时绑定宿主机回环和 Docker 内部网关 `172.17.0.1`。

服务器验收后，Mac 上本项目的 28 个容器、3 个 Kuscia 卷、已迁移镜像及用户确认归属的历史镜像已清理。数据库、日志和旧本地备份已先归档到服务器，再移除本地副本。源码、Git 历史、配置、文档和手写补丁保留。逐项记录见本目录 `local-*-cleanup.json` 及 `historical-images-cleanup.json`。

## 资源采样

重启后采样：本项目容器工作集约 **4.52 GiB**，三个 Java 后端 RSS 合计约 **2.18 GiB**，合计约 **6.70 GiB**。这是当时的采样估算，不是任务高峰上限；不包含服务器原有业务和内核开销。

当时服务器磁盘剩余约 **174 GB**。源码目录、持久目录、备份目录和容器资源明细见 `resources-final.json`；目录统计不包含 Docker 镜像及数据卷，不应相加后当作项目全部磁盘占用。

本次迁移验收对应现有已实现的四协议拓扑和上述真实任务；原目录中尚未接入的 BaaS/dtx-manager 等历史模块，没有因迁移自动补齐功能。PaddleDTX 原生控制台页面已恢复，但其 `/dtx/v1/` 管理后台仍未接入，数据、模型、账户管理不能据此认定已完成；本次预测验收走统一平台的原生 requester/executor 链路。
