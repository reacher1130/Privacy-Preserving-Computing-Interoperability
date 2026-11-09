# 隐私计算开放互联平台

Alice（隐语、BFIA、FATE、PaddleDTX）、Bob（BFIA）、Kimi（隐语），包含统一前端、原生链桨管理台、FATE Guest/Host Board、算法回归和迁移打包。

当前交付状态（2026-11-09）：BFIA suite 镜像已公开，公司网页八算法运行、刷新和报告导出已验收。完整平台发布仍待 Paddle 执行器的 CGO/存储修复验收和最终清单；当前源码尚无 `releases/runtime.json`，默认 `all` 会在发布清单检查处停止。以下为完整发布就绪后的入口用法。

## 新机器一键部署

在 **Linux + systemd** 主机执行。amd64 原生部署；arm64 自动创建 Ubuntu amd64 QEMU 虚拟机并执行相同流程（模拟运行较慢）。默认网页仅绑定本机回环地址；局域网使用下面的目标机实际地址和允许访问的网段。

```bash
git clone --recurse-submodules https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability.git
cd Privacy-Preserving-Computing-Interoperability
sudo bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

完整发布配置就绪后，`all` 安装运行依赖，按根目录 `releases/runtime.json` 的固定校验和下载已发布程序和镜像，初始化独立节点和数据库、启动服务，并运行真实公开样例。新机器不编译算法或平台，也不安装 Go/Maven/Node/Bazel。任何阶段失败会停止并返回非零状态。不要在现有办公部署上运行首次安装；脚本会拒绝接管未受本工具管理的容器/服务。

```bash
bash deploy.sh --help
bash deploy.sh sync                              # 更新当前 Git 分支和固定子模块
sudo bash deploy.sh check                        # 检查目标机依赖、目录和网络
sudo bash deploy.sh build                        # 维护者显式源码构建，需编译工具和资源
sudo bash deploy.sh up --no-tests                 # 部署已有构建，不运行新样例
sudo bash deploy.sh run                          # BFIA 八算法、FATE、隐语、链桨训练/预测
sudo bash deploy.sh status
sudo bash deploy.sh package --with-images --output /mnt/usb/ppci-release
bash deploy.sh package --source-only --output /tmp/ppci-source.tar.gz
bash deploy.sh clean                             # 查看可清理缓存
bash deploy.sh clean --apply
```

源码包命令也可在 macOS 使用。完整离线包可在已完成部署或构建的 Linux amd64 环境生成，ARM 会转交虚拟机打包并取回。详细参数、迁移、账号位置和平台边界见根目录 [DEPLOYMENT.md](DEPLOYMENT.md)。

网页 BFIA 算法中心的“一键运行 8 个算法”通过 Kuscia 启动同一个固定版本镜像，镜像内运行双方公开样本，返回真实数值结果、协议校验和 Alice/Bob 日志。它不挂载宿主源码、不调用容器内 Docker，也不在点击时编译。镜像包含 SGB、HE-WOE、ECDH-PSI、SS-LR、SS-XGB、SS-Pearson、SS-VIF、SS-Compare；这是公开样本验证，真实机构分布式任务仍使用平台各组件的任务入口。

## 项目目录

`platform/` 是原来的 `NewProject/`，名称来自早期集成目录，现已改为明确的核心平台目录。

| 目录 | 内容 |
| --- | --- |
| `platform/` | 隐语、BFIA、FATE、统一前后端、集成脚本、补丁、样例和验证文档 |
| `PaddleDTX/` | 链桨上游基础源码子模块；定制构建源码位于 `platform/thirdparty/` |
| `scripts/` | 根部署入口使用的构建、运行、打包及校验程序 |
| `images/bfia-suite/` | 八算法自包含镜像、受控构建上下文与运行入口 |
| `releases/runtime.json`（待生成） | 完整发布验收后封存的程序和镜像清单入口 |
| `specs/` | 功能设计与实施记录 |
| `dist/` | 本地导出的源码包，不纳入 Git |
| `.local-backups/` | 私有历史归档、节点身份和备份，不纳入 Git |

源码目录改名不迁移已部署服务器的运行数据；`/opt/ppci/NewProject/` 等历史运行路径保持兼容。旧验收证据中的原始路径保留原样。

## 源码和数据

主仓和全部 15 个递归子模块均可匿名克隆。2026-11-06，主仓、SecretFlow 定制仓和前端定制仓从脱敏快照建立公开历史；各自原库改名为 `原名-private-archive-20261106` 并保持私有。旧克隆应重新克隆公开版本，避免把原历史推回公开库。此前私有源码包保留且不公开分发；迁移使用当前公开源码重新打包。

子模块固定到已归档的工作版本；`sync` 使用当前分支的 fast-forward 更新，不擅自升级各上游主线。FATE 的兼容修改由 `scripts/apply-source-patches.py` 幂等应用。干净 clone 同样包含经筛选的链桨历史构建源码及其校验清单，无需访问原办公目录。

部署默认隔离三个目录：仓库源码、`/opt/ppci-build` 构建产物、`/opt/ppci` 运行数据。打包只导出受控源码、程序和镜像，不复制实际数据库、私钥、上传文件、账本、模型或任务结果。上游仓库自带的公开演示身份/样本属于源码示例，不能用于生产。

原 `privacy-computing-interconnectivity/` 的未合并定制源码及旧节点目录已移入 `.local-backups/layout-20261109/` 的私有归档，原有源码包保留在 `dist/`。`clean` 仅清理明确可再生成且未被 Git 跟踪的依赖/构建缓存，保留构建必需的已跟踪 `.cache`。

## 验证记录

2026-11-06，[Ubuntu 22.04 / 24.04 公开 CI](https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability/actions/runs/42202219257) 均通过匿名递归克隆、固定源码检查、49 项部署测试、3 项运行状态测试及 `bootstrap --native` / `check --native`。另在隔离 Ubuntu 24.04 amd64 环境完成相同克隆、测试和预检；这些检查不包含完整平台构建与算法运行。

此前办公实机验收：[2026-11-02 恢复记录](platform/docs/office-recovery-20261102/README.md)、[链桨模型保存与预测](platform/docs/office-recovery-20261102/paddledtx-crossday-acceptance.md)、[BFIA 八算法数值和协议](platform/docs/bfia-eight-algorithms-numerical-protocol-20260914.md)。这些历史结果不代表新的一键部署已完成所有发行版/ARM 实机验收。当前脚本验证范围见 [部署说明](DEPLOYMENT.md)。

2026-11-09，C4 源码 `0daa7a361ecb9c68636048cf3145810db38bb52f` 的 104 项轻量检查通过。公司浏览器运行 `2604c8e1…` 的八项数值/协议检查、刷新恢复及导出与 API 一致性已通过；完整镜像层匿名拉取、修复后的空白 VM 全量 `all` 和最终发布清单仍待完成。
