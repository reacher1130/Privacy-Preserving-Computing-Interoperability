# 家庭与办公 Linux 环境

家庭主机 `192.168.31.49:22`，办公主机 `192.168.45.101:2222`。两者使用独立运行数据；SSH 密码不写入配置或脚本。

目录约定：

| 目录 | 用途 |
| --- | --- |
| `/opt/ppci-source` | Git 源码与当前开发修改 |
| `/opt/ppci-build` | 隔离构建目录；家庭主机指向 `/home/ppci/build` |
| `/opt/ppci` | 已部署程序、配置、节点运行目录 |
| `/srv/ppci` | 后端辅助持久化状态 |
| `/var/log/ppci` | 构建、测试、服务日志与验收证据 |
| `/home/ppci/releases` | 可带回办公网的离线发布包 |

## 日常开发

在仓库根目录执行；SSH 会使用正常的密钥或密码认证。`sync` 不启动、停止或发布服务，也不删除目标端额外文件。

    python3 NewProject/scripts/environment.py home info
    python3 NewProject/scripts/environment.py home sync --dry-run
    python3 NewProject/scripts/environment.py home sync
    python3 NewProject/scripts/environment.py home build frontend
    python3 NewProject/scripts/environment.py home build backend
    python3 NewProject/scripts/environment.py home build kimi

也可直接 SSH 进入家庭主机，在 `/opt/ppci-source` 开发；在不同设备同时修改同一文件前，先比较并合并 Git 变更，避免用 rsync 覆盖另一端的未提交修改。

首次初始化完成后才可以使用发布与健康检查：

    python3 NewProject/scripts/environment.py home deploy frontend
    python3 NewProject/scripts/environment.py home deploy backend
    python3 NewProject/scripts/environment.py home deploy kimi
    python3 NewProject/scripts/environment.py home status

## 新主机初始化

已经安装的家庭工具：Anolis 23.5、Docker 29.5.1、Dragonwell Java 21、Node 22、pnpm 8.8.0、Maven 3.9.9、Go 1.26.6、nginx。Java 21 路径为 `/usr/lib/jvm/java-21-openjdk`，Maven 和 pnpm 位于 `/opt/ppci-tools`。项目构建脚本显式使用这些路径，不依赖系统默认 Java 8。

仅用于新主机；`prepare` 会拒绝覆盖办公迁移环境已有的 systemd 服务。

    python3 /opt/ppci-source/NewProject/scripts/environments/provision.py prepare
    bash /opt/ppci-source/NewProject/scripts/environments/build-runtime.sh kuscia
    bash /opt/ppci-source/NewProject/scripts/environments/build-runtime.sh adapter
    python3 /opt/ppci-source/NewProject/scripts/environments/provision.py fate
    python3 /opt/ppci-source/NewProject/scripts/environments/provision.py kuscia
    python3 /opt/ppci-source/NewProject/scripts/environments/provision.py platform
    python3 /opt/ppci-source/NewProject/scripts/environments/provision.py gateway

`kuscia` 阶段运行三个特权容器；`platform` 阶段启用三个开机自启的 Java 服务。用户在 2026-09-12 明确授权后，两步均已执行。`upgrade-kuscia` 仅升级本工具创建且具有持久数据卷的家庭节点，并保留停止状态的旧容器与配置备份。

Kuscia 内部网络固定为 `192.168.117.0/24`：Alice/Bob/Kimi 使用 `.2/.3/.4`，原生 FATE Guest/Host 使用 `.20/.21`。只把网页端口向家庭 LAN 开放；内部 API 绑定回环或 Docker 网桥。官方 FATE 镜像的原生 Flow 数据使用独立 Docker 卷，重建节点配置不会覆盖办公数据。

FATE 官方离线镜像来源：

[FATE 单机部署说明](https://github.com/FederatedAI/FATE/blob/master/deploy/standalone-deploy/README.zh.md)。使用其中 2.2.0 的腾讯云 COS 离线包；Docker Hub 在家庭主机解析异常，官方文档所列腾讯镜像仓库的该标签返回不存在。

## 测试与目前状态（2026-09-12）

- 源码已同步约 1.7 GB，包括 Git 历史与本次 FATE 模板修改。
- 前端、Alice/Bob 后端、Kimi 后端、互联 Kuscia 与 FATE 适配器构建通过。
- 前端 27 项 Jest 测试与 TypeScript 检查通过；FATE 适配器 Go 测试通过。
- FATE Guest/Host、FATEBoard、静态前端已启动。
- 原生 PSI 作业 `202609121207570091360` 成功。
- 原生 PSI + 两轮 Coordinated LR 作业 `202609121208123546570` 成功，Guest/Host/Arbiter 任务均成功。
- 原生证据：`/var/log/ppci/acceptance-20260912120731`。
- Alice、Bob、Kimi 的 Java 服务与 Kuscia 节点均已启动，开机自启已启用；三个工作区均已在浏览器加载。
- Kimi 保持原生后端。家庭网关仅为共享前端提供只读的固定隐语模式配置（`GET /api/v1alpha1/config/protocol`），该配置不代表新增协议执行能力。
- 浏览器模板 PSI：平台 `fj-b61d1d165db341a5` → 原生 `202609121352297100000` 成功。
- 浏览器画布 PSI + 两轮 LR：平台 `fj-b8db5d62983a4e57` → 原生 `202609121359079384560` 成功。
- PaddleDTX 的 3 个链节点、3 个数据拥有方、3 个存储节点、3 个执行器和可视化服务已启动。
- 链桨网页训练 `bfde09d0-0b77-485e-8a9d-99d598bc9441` 已完成，使用仓库公开 Boston 样例；两方训练产物保存在执行器模型卷。此验收证明执行链路，不代表模型质量评估。
- FATEBoard 演示账号 `admin / admin` 登录成功。
- 平台验收证据：`/var/log/ppci/acceptance-platform-20260912`。
- 升级后网页 PSI `fj-7461a62c40ea4633` 成功，列表自动更新为 SUCCESS。
- 原生隐语 Alice/Kimi PSI `home-native-psi-20260912223847` 成功，双方输出均为已知交集 `2、3`。
- BFIA Python SGB、HE-WOE 回归通过，双方实际收发消息证据见 `/var/log/ppci/bfia/python/home-python-20260912`；这是同机双进程算法测试。
- BFIA 当前 C++ 引擎构建完成，六项回归（ECDH-PSI、SS-LR、SS-XGB、SS-Pearson、SS-VIF、SS-Compare）均通过，双方容器具有不同 IP，均有实际通信证据；见 `/var/log/ppci/bfia/cpp/home-current-20260912`。
- BFIA 原生 Kuscia 双方 PSI `home-bfia-psi-20260912233315` 成功，Alice/Bob 实际输出交集均为 `2、3`；证据见 `/var/log/ppci/acceptance-bfia-20260912233315`。此项通过 Kuscia 调度执行；未将它表述为网页 BFIA 项目编排验收。
- 当前 C++ 运行镜像约 109 MB，`ppci/bfia-cpp:home-20260912` 的镜像 ID 为 `sha256:5195510aa1043e5fe6e8d7c14162941796c148328ffb46d3407c50053729f36c`，七个组件镜像别名已导入 Alice/Bob。
- 全量健康检查通过；18 个运行容器、3 个 Java 后端、双方 FATE 身份、3 个链桨执行器、计算镜像与 BFIA 合作目录均就绪。已检查开机自启配置，未执行整机重启验收。

原生独立回归脚本会创建带时间戳的公开样例数据与任务，保留既有数据：

    python3 /opt/ppci-source/NewProject/scripts/environments/native-smoke.py

这项原生测试不替代“总平台 → Kuscia → 适配器 → 原生 FATE”的端到端验收。

## 网页入口与链桨初始化

家庭网页入口：Alice `http://192.168.31.49:18101`、Bob `http://192.168.31.49:28101`、Kimi `http://192.168.31.49:38101`、FATEBoard `http://192.168.31.49:19383`、链桨原生控制台 `http://192.168.31.49:18511/dtx/console/`。

链桨使用独立的本地演示链和公开样例账号；源代码与公开模板来自 PaddleDTX 仓库。初始化保留账本、文件、模型和任务记录：

    bash /opt/ppci-source/NewProject/scripts/environments/build-runtime.sh paddle
    python3 /opt/ppci-source/NewProject/scripts/environments/paddle-provision.py all
    python3 /opt/ppci-source/NewProject/scripts/environments/paddle-demo-data.py

总平台的链桨任务页使用 `executor1,executor2`，文件 ID 见 `paddle-datasets.json`。样例授权的有效期独立于文件期限；授权到期后需由对应数据拥有方重新确认，不能把“已发布”当作训练完成。

## 带回办公网

家庭主机生成离线包：

    python3 /opt/ppci-source/NewProject/scripts/environments/export-release.py --with-images

包包含 `artifacts.tar.gz`、`images.tar.gz`、`manifest.json` 和 `SHA256SUMS`。只包含程序、脚本、镜像与源代码版本标识，不包含运行数据库、节点证书、用户上传数据集、模型或任务结果；官方镜像自带的公开样例保持原样。清单中的 Git `status` 会记录未提交的开发修改。

完整包覆盖修复后的 Kuscia、当前前端、链桨构建产物、FATE、隐语和 BFIA C++/Python 运行镜像（18 个镜像标签，重复层只保存一次）。源码及未提交修改仍以源码同步目录为准；离线程序包不能代替源码备份。

带走前将整个时间戳目录复制到笔记本或移动存储；回到办公网后，再复制到办公主机的临时发布目录，校验并解压到构建目录：

    sha256sum -c SHA256SUMS
    docker load -i images.tar.gz
    tar -xzf artifacts.tar.gz -C /opt/ppci-build

办公环境已经有完整运行目录，使用原来的备份、健康检查与回滚发布流程：

    bash /opt/ppci-source/NewProject/scripts/linux-migration/deploy-built.sh frontend
    bash /opt/ppci-source/NewProject/scripts/linux-migration/deploy-built.sh backend
    bash /opt/ppci-source/NewProject/scripts/linux-migration/deploy-built.sh kimi
    ppci-platform status

更换 Kuscia 镜像涉及现有办公节点的持久化目录与证书，不能直接运行新机初始化脚本替换。先保留办公节点、卷与路由配置，再做针对该运行拓扑的升级验收。办公服务器目前不在家庭 LAN 可达范围内，尚未执行本次办公部署。

## BFIA 首次构建

当前源码需要 Bazel 6.5.0 和 SPU pin `74c6d54e5bff9e5d35ab5a73dda98cd9ccf0bfc8`；不能用旧官方镜像中的二进制替代。

    python3 /opt/ppci-source/NewProject/scripts/environments/build-bfia.py build
    python3 /opt/ppci-source/NewProject/scripts/environments/build-bfia.py base
    python3 /opt/ppci-source/NewProject/scripts/environments/build-bfia.py image
    python3 /opt/ppci-source/NewProject/scripts/environments/build-bfia.py python
    python3 /opt/ppci-source/NewProject/scripts/environments/build-bfia.py import
    python3 /opt/ppci-source/NewProject/scripts/environments/bfia-partners.py

Bazel 可执行文件放在 `/opt/ppci-build/tools/bazel-6.5.0`，脚本校验 SHA-256。构建缓存放在 `ppci-bfia-bazel-cache` 卷；可通过运行时环境变量 `HTTPS_PROXY` 指定构建下载代理，代理地址不写入源码或运行镜像。运行时基础镜像 `ppci/bfia-runtime-base:bookworm-20260912` 基于 Debian bookworm-slim，仅安装 ca-certificates、curl 和 libgomp1；编译器不进入运行镜像。

原生隐语与 BFIA 的生成样例回归：

    python3 /opt/ppci-source/NewProject/scripts/environments/secretflow-smoke.py
    python3 /opt/ppci-source/NewProject/scripts/environments/bfia-smoke.py

它们只创建专用样例、任务和验收结果，不清理已有数据。

全量启动检查会核对 18 个运行容器、3 个后端、原生 FATE 双方身份、3 个链桨执行器，以及 Alice/Bob/Kimi 所需计算镜像是否已导入。健康检查通过不替代具体算法或网页业务验收。

`bfia-partners.py` 仅初始化同机 Alice/Bob 的演示合作目录，期限 30 天；已配置双方签名通道时，由 Alice 申请、Bob 确认同一个合同。脚本不授权数据集，发现既有合作记录时不会覆盖。
