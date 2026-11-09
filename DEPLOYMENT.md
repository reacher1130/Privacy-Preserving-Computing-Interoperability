# 全量部署、算法运行与迁移

根目录 `deploy.sh` 是统一入口。目标是独立开发/演示环境；复用既有业务库、链或办公节点的升级，应沿用相应备份/升级流程。

程序包和 14 个运行镜像已公开，根目录已固定发布清单；公司网页八算法运行、刷新和报告导出已验收。公司服务器内的新 Ubuntu 24.04 VM 已连续完成完整 `all`，全量流程不编译平台或算法。发行版、镜像缓存及浏览器/API 的证据范围分别记录如下。

核心集成源码现位于 `platform/`（原 `NewProject/`）。部署入口、子模块版本和外部接口保持不变；现有服务器的运行数据路径仍兼容 `/opt/ppci/NewProject/`。不要因源码目录改名而手动移动数据库、身份或容器挂载目录。

## 系统和资源

| 主机 | 执行方式 | 验证边界 |
| --- | --- | --- |
| Ubuntu 22.04/24.04、Debian，amd64 | apt 安装运行依赖、JRE，拉取已编译程序和镜像 | Ubuntu 22/24 CI 匿名递归克隆、bootstrap/check 通过；Ubuntu 24.04 新 VM 完整 all 连续通过（使用已验证镜像缓存及已有测试状态）；Debian 未实测 |
| CentOS Stream 9/10、兼容的 RHEL/Rocky/Alma/Anolis，amd64 | dnf 安装运行依赖；拉取相同 amd64 镜像，保留 SELinux | 本轮公司服务器为 Anolis 8.10；不能据此宣称所有 CentOS 版本均已实测 |
| 上述 Linux arm64/aarch64 | Ubuntu amd64 cloud image + QEMU TCG 整机模拟 | 已做配置/命令/安全边界测试，未做 ARM 实机部署验收；明显慢于原生 |
| macOS | 本地缓存清理、完整源码导出 | 不在 macOS 原生安装 Linux 服务 |
| CentOS 7/8 等已停止维护系统、32 位 ARM、其他 CPU | 不承诺自动安装；先准备受支持的 Linux 主机/虚拟机 | 不把架构检测通过视为全栈兼容 |

建议至少 8 个逻辑核、24GB 内存、100GB 可用磁盘；ARM 宿主机还需给模拟 VM 预留资源。默认 VM 分配 4 vCPU、16GB 内存。首次拉取程序、运行依赖和镜像需要网络；下载失败会退出，可以处理网络后重试。默认部署无需编译。旧系统缺 Python3.9+ 时应先升级运行宿主；Anolis 8 的入口会选用已有的 Python3.11。

## 一键执行及拆分阶段

```bash
sudo bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

将 IP/CIDR 改为目标机器实际地址和允许访问的内网。无参数时默认 `all`，网页仅开放 `127.0.0.1`。完整发布配置就绪后，安装器安装 Docker、nginx、Python、JRE 等运行依赖，启用对应服务，然后核对 `releases/runtime.json` 指定清单的 SHA256、程序包 SHA256、镜像仓库摘要和 Docker image ID，再部署。默认流程不安装或调用 Go/Maven/Node/Bazel/C++ 编译器。不卸载已有 Docker，不删除已有卷，不关闭 SELinux/防火墙。与现有环境冲突时停止，避免把已有环境当作空机器。

`--no-tests` 只跳过部署后的新样例执行，仍拉取发布程序并进行健康检查。`up` 使用已有程序/镜像；维护者显式执行 `build` 才安装编译工具并从源码构建，构建结果不自动公开发布。`sync` 拉取当前 Git 分支并同步固定子模块。源码包没有 `.git` 时，`sync` 只验证源码清单。

源码、构建目录、运行目录不能互相包含。默认使用当前仓库、`/opt/ppci-build`、`/opt/ppci`；可用 `PPCI_BUILD_ROOT` / `PPCI_ROOT` 设置独立绝对路径：

```bash
sudo env PPCI_BUILD_ROOT=/data/ppci-build PPCI_ROOT=/data/ppci \
  bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

内部 Docker 网络为 `192.168.117.0/24` 和 `172.31.1.0/24`。目标网段冲突必须先解决。VM 内使用私有 NAT，外部网页端口映射到宿主机；非回环映射由专用 iptables 规则限制来源 CIDR，不刷新其他防火墙规则。

Kuscia 的固定镜像身份使用 Docker classic 镜像存储。Docker 29 新安装默认使用 containerd 存储；`bootstrap` 仅在该存储下没有任何容器或镜像时，备份原 daemon.json、保留其他配置并自动启用 classic。已有数据时停止并保留原存储，应使用独立新主机或虚拟机。预检、离线导入和镜像打包也检查这一条件，不通过放宽镜像校验来兼容。公司 Docker 26 classic 和空白 Ubuntu 的 Docker 29 自动配置均已验证。

## 全量覆盖和入口

| 内容 | 入口/行为 |
| --- | --- |
| Alice 统一平台 | `http://目标机IP:18101`；隐语、BFIA、FATE、PaddleDTX |
| Bob / Kimi | `http://目标机IP:28101` / `http://目标机IP:38101` |
| FATE Guest / Host Board | `http://目标机IP:19383` / `http://目标机IP:19384`；独立会话和目标机生成的账号 |
| 链桨原生管理台 | `http://目标机IP:18511/dtx/console/`；签名登录、管理库、上传/下载、只读链上 UUID 查询 |
| BFIA | 七个组件镜像别名、合作目录、统一平台八算法中心；八算法使用独立自包含镜像 |
| 原生隐语 | Alice/Kimi Kuscia、SecretFlow 计算镜像、公开 PSI 样例 |
| FATE | 双 Flow、字符串 party ID 兼容、适配器与 Kuscia AppImage、双 Board |
| PaddleDTX | 三链、三个数据拥有方、三个存储、三个执行器、定制计算/管理合约、MySQL、原生管理台 |

目标机生成的凭据只保存在目标私有目录：链桨为 `/opt/ppci/native/dtx-manager/private/credentials.json`，FATE 为 `/opt/ppci/fateboard/{guest,host}/credentials.properties`。自定义 `PPCI_ROOT` 时路径随之变化。不要把这些文件加入 Git 或发布包。统一平台沿用各模块自身的账号初始化规则。

这是公开样例的独立演示链，包含上游公开测试身份/合约账号。不要用于真实机构或资产。新部署使用 Local 模型/预测持久卷；既有 XuperDB 数据和模型不包含在程序包中。部署显式关闭健康跳过参数，不改写心跳评分、不绕过存储门禁。新节点尚不满足健康条件时，相关样例会失败，需要待节点就绪后重跑。外部 BaaS 区块浏览器不属于当前四平台运行栈，需要另配目标服务，不能沿用历史外部地址。

## 算法一键运行

```bash
sudo bash deploy.sh run
```

依次运行：BFIA 的 SGB、HE-WOE、ECDH-PSI、SS-LR、SS-XGB、SS-Pearson、SS-VIF、SS-Compare；FATE PSI 和 PSI+联合逻辑回归；隐语 Alice/Kimi PSI；BFIA Alice/Bob Kuscia PSI；链桨公开 Boston 纵向线性训练、模型读回和预测。任一失败返回非零状态。

网页八算法按钮和 CLI 共用固定执行器：创建一项 Alice Kuscia 任务，在镜像内启动双方公开样本，数值和协议校验后取回报告及 16 份日志。镜像已经包含 Python 依赖、C++ 引擎、公开数据和校验器，不挂载宿主源码或 Docker socket。任务 ID 与网页运行 ID 相同，可刷新查看状态、双方日志和下载报告。这个样本入口验证双方协议与数值，不等同于跨机构独立部署验收。

镜像构建方法、独立 `docker run` 和输出结构见 [镜像说明](images/bfia-suite/README.md)。发布清单记录不可变仓库摘要和本地别名；部署后固定配置位于 `/opt/ppci/etc/bfia-suite.json`，结果位于 `/var/log/ppci/bfia-suite/runs/运行UUID/`。自定义运行目录时相应路径随之变化。

链桨只批准**本轮 task UUID + 本轮文件 + 对应执行器公钥**的公开样例申请，有效期两小时，保留其他申请；核对双方非空本地模型、预测 ID 交集/唯一性及有限数值。摘要写在 `/var/log/ppci/paddle-smoke-*`。超时后用原输出目录恢复同一任务；将示例中的 `python3.11` 换成目标机的 Python3.9+ 命令，Anolis 8 的默认 `python3` 可能仍为 3.6：

```bash
sudo python3.11 scripts/paddle-smoke.py --output /var/log/ppci/paddle-smoke-实际目录
```

统一平台两个链桨算法说明条目仍是说明性演示，不计入 BFIA 八算法报告。CLI 原生样例、健康通过和本次自动化测试不替代完整浏览器业务、真实机构互联或生产模型质量验收。

## 打包和迁移

有完整 clone 的机器均可导出已跟踪源码、固定子模块实际工作文件及经筛选的链桨历史构建源码，无需 `.git`、本机旧目录、缓存或身份：

```bash
bash deploy.sh package --source-only --output /mnt/usb/ppci-source.tar.gz
tar -xzf /mnt/usb/ppci-source.tar.gz -C /新源码父目录
cd /新源码父目录/ppci-source
sudo bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

`.ppci-source.json` 记录文件校验、Git 版本和是否有未提交修改。历史证据的外部绝对软链接会剔除，正常相对源码链接保留。新文件应先审查并纳入 Git，再制作包。

只分发从当前公开历史生成的包。2026-11-05 的私有旧源码包包含原历史快照，仅保留备份，不能作为公开发布包。

在已成功部署或构建全栈的 Linux 环境生成程序/镜像离线包，无需重新编译：

```bash
sudo bash deploy.sh package --with-images --output /mnt/usb/ppci-release
```

输出 `source.tar.gz`、`artifacts.tar.gz`、`images.tar.gz`、`manifest.json`、`SHA256SUMS`，以及可用时的独立 Java/static-rg 工具包。镜像验证 amd64 架构并记录 image ID，共享层只导出一次。ARM 在 VM 内打包，再取回宿主机指定位置。

**离线恢复要求目标系统已具备 Docker、systemd、Python3.9+、PyYAML、nginx、rsync 等系统依赖。** 包不包含各发行版 deb/rpm 仓库。新 ARM 主机还需要预先准备的 VM（或在线 bootstrap 一次）；空白 cloud image 不含运行依赖。

```bash
cd /mnt/usb/ppci-release
sha256sum -c SHA256SUMS
tar -xzf source.tar.gz -C /opt
cd /opt/ppci-source
sudo bash deploy.sh all --offline /mnt/usb/ppci-release \
  --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

恢复先校验完整清单和摘要，再解包、导入并核对镜像；跳过下载/编译，创建目标自己的状态。不迁入原环境实际数据库、私钥、账本、上传数据、模型、任务结果。业务迁移须另行备份/恢复，程序包不是业务备份。

## 本次验证

2026-11-05 本机清理约 1GB 已忽略依赖/构建缓存，保留历史定制集合、备份、节点身份和已跟踪的 Bazel 覆盖源码；原完整源码包已生成、解包、校验并在无 `.git` 的副本中测试。8 个定制链桨 Go 程序完成 Linux amd64 交叉编译；管理端安全回归、元数据兼容及原生前端测试和生产构建通过。该旧源码包现在仅作私有备份。

2026-11-06，主仓及两个含旧凭据历史的定制仓以独立脱敏快照公开，原历史留在私有归档；另外五个自有模块公开。独立 Ubuntu 24.04 amd64 环境无凭据克隆全部 15 个递归子模块，固定版本匹配；49 项部署/打包/VM/授权测试及 3 项运行状态测试通过，`bootstrap --native` 和 `check --native` 成功。[公开 CI](https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability/actions/runs/42202219257) 在 Ubuntu 22.04、24.04 分别完成相同克隆、测试和引导检查。修复了独立 JDK 未加入 PATH 以及新机下载请求失败的问题。

公开快照 `274c831` 的本地源码包已生成，16,436 个文件逐项匹配校验清单；不含 Git 元数据，已核对 10 处令牌字段脱敏及两份敏感文件移除。该包没有全栈构建产物或运行镜像。

以上为 2026-11-06 的源码交付记录，不代表新版镜像交付或 QEMU TCG 的 ARM 实机验收。以目标机真实退出状态、任务输出和浏览器验收为准。

2026-11-09，本轮构建、镜像下载和运行全部在公司服务器进行。首轮 C2 脚本版本为 `d25e976`；除补齐 Kimi 必需源码的构建外，该轮组件构建收据保留实际版本 `8196539`，不改写为交付脚本版本。Kimi 使用公开子模块 `00cda30`；算法使用 SecretFlow 固定版本 `3b2793a`。C++ 引擎复用已验收二进制 `bae5160e4f794a9ec0337e707efae327d0354e0be235b8ebe67ec439251c7e00`，本轮没有重新编译该二进制。

C4 构建源码为 `0daa7a361ecb9c68636048cf3145810db38bb52f`，已加入原生 Paddle 存储配置兼容及 executor 的 CGO/SQLite 构建修复。新 executor 的 SHA256 为 `dea11378edb3a853bf714d07b3aeaed8a5c10271c59cc732b7ec60e9e562b859`；公司主机和新 DAI 镜像内均通过动态链接检查、实际项目 DAO 建表及 SQL 插入/查询，确认使用真实 SQLite 驱动。后续部署脚本修复不改写这些构建收据。

最终 suite 镜像 ID 为 `sha256:b5288bc2a7fe025838c10af392f9dbfba0841bc2a14a0ea8f046f6d594ed9a26`。公司平台同一网页 API 新建运行 `e325aff5-d13e-4565-9eb7-010846453f4e`，对应真实 KusciaJob 同 UUID，约 93 秒完成；33 次刷新保持同一运行，8 项数值和协议校验通过，服务器保留 16 份完整双方日志及协议报告中的 SHA256。API 可读取日志；超过 512KiB 时返回带提示的尾部。此次验证没有重启服务或容器，原有 31 个业务容器 ID 保持不变。下述数值和报告摘要仅属于这次 API 运行。

| 算法 | 本次数值结果 |
| --- | --- |
| SGB | 569 条公开训练样本，重算 AUC 0.9942920564；不代表泛化能力 |
| HE-WOE | 30 特征、300 个分箱，最大绝对误差 0 |
| ECDH-PSI | 交集 128 条，与预期 ID 完全一致 |
| SS-LR | 最大误差约 0.00001295，小于 0.00002 |
| SS-XGB | 最大误差约 0.00067664，小于 0.004 |
| SS-Pearson | 最大误差约 0.00030899，小于 0.01 |
| SS-VIF | 最大误差约 0.00164063，小于 0.03 |
| SS-Compare | 核验 256 项双方列比较 |

报告 SHA256 为 `5c5e7266868ef7a4f1aa50ef33277592c708215be4b39674148558221f630283`。服务器私有验收目录为 `/opt/ppci-build/bfia-suite-release-20261109/web-api-integration/`；旧执行器及配置备份在 `/var/backups/ppci/releases/bfia-suite-20261109/`，不放入公开程序包。

随后公司平台已使用公开 suite 摘要 `sha256:fa639734c9bc5b7d778c1289a2ed13ef5661a01edf2133bbb67b52e02a159d7c`。浏览器运行 `2604c8e1…` 的八项数值/协议标志全部通过，重新加载保留同一运行；导出的 JSON 与该运行 API 报告一致，SHA256 为 `31ac0e08b0c2b6be3c8d7fb5825683db1c98ed46d99eef1c56d670499bfa76db`。

该 suite 摘要的 19 个压缩镜像层已全部匿名下载并逐层核对 SHA256，总载荷 780,833,522 字节；使用空认证目录，不登录仓库、不读取 Docker 缓存。网络中断后采用匿名 Range 续传，保留失败记录，不宣称单次无中断冷拉取。最终归档通过完整 `crane validate --tarball`，精确匹配上述镜像 ID 和 linux/amd64；归档 SHA256 为 `0bc46dfe2e5b1a69739fd2ad67c218b58898e1c601b0e78a4d1b8a9c19547bbb`。

本轮[Ubuntu 22.04 / 24.04 公开 CI](https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability/actions/runs/42628281508) 均通过固定提交 `e6866ff` 的匿名递归克隆、115 项轻量检查、3 项运行状态检查和 runtime bootstrap/check。首次 Pending/ContainerCreating 空镜像 ID 的等待修复保留了运行后的固定镜像身份及零重启要求。

最终公开运行版本为 `runtime-20261109-50f40e9`，清单 SHA256 为 `12e20f183c250d5ec0bf2080ca8fa142711fb8a8db4f855cfcc9ab08edd871cf`，程序包 409,996,490 字节、SHA256 为 `52f9427de3d5e41d56b60f55a9c187a7124a22f70b38846f9ecafc969e577fcc`。其余组件保留实际 B/C4 构建收据；本次只修正业务 C++ 入口及链桨 SDK，未重编译 C++ 算法。C++ 镜像 `9aa7aec3…` 在双节点真实握手后输出交集 `2,3`；新 DAI 镜像 `dd243f53…` 包含 CGO1 executor（`1646ad74…`）和 CGO0 requester（`0aebfd7d…`），executor 的动态链接和真实 SQLite DAO 检查通过，两程序镜像内哈希匹配。SDK 两处 XDB 查询改发 `paddlempc` 合约，管理合约 `data`、签名、审批、到期和解密检查不变；真实 SDK RPC 回归及正常静态检查通过。

新 Ubuntu 24.04 VM 已完成运行依赖/JRE 安装、Docker 29 空存储自动配置、部署及分项样例，安装前后没有 Go/Maven/Node/Bazel/C++/javac 编译工具。八算法 `b2ccf1c6…` 的数值/协议和 16 份日志通过；FATE PSI/LR、隐语 PSI、BFIA 双节点 PSI 通过。链桨原训练任务 `31901c69…`、预测任务 `bc3d2833…` 均 Finished，双方模型 683/912 字节，签名读回 50 行预测，ID 等于输入交集且数值有限；四份授权均限定对应 task/file/executor。

suite 使用上述完整匿名归档，其余运行镜像在公司网络连续 EOF 后预载与公开清单相符的内容缓存；两个修复镜像也先在公司构建并验证。最终发布清单及 14 个镜像/20 个别名的 registry 元数据已匿名校验。测试 VM 使用 `4a9be60` 源码连续执行原样 `bash deploy.sh all --native`，929.17 秒退出 0：全新公开程序完整无凭据下载并匹配 `52f9427d…`，部署和服务检查、八算法 `f1720602…`、FATE PSI/LR、隐语/BFIA PSI及链桨训练/预测均通过，前后宿主编译器均不存在。最后一轮模型 683/920 字节，预测 50 行且 ID 交集/有限数值检查通过。该次保留既有测试应用状态并使用已验证镜像缓存，不计作一次零应用、零镜像状态的冷启动。

完整 all 后通过正常协议接口切换 BFIA，再由新后端 JAR（SHA256 `029f5eca7db64b223da8f8c8e36277972b3042a6e38830ce75ca51587983fdbb`）唯一发起 API 运行 `5fd526cc-60e1-4e20-b584-839ca0d2317d`。29 次刷新保持同一运行，8 项数值/协议、16 份双方日志通过，对应 KusciaJob UID `391eab62-4d49-43e8-be5f-def6af6a8072` 为 Succeeded，固定 fa639/b528，`local_build=false`。API 验收报告 JSON 的 SHA256 为 `21551155faab148e8e9c011682e58a51ca8e7855999590863215ddab09552b54`；这次是新 VM 的 API 验收，不冒称浏览器点击或混用前述公司浏览器 `2604c8e1…` 的导出报告。

早期失败 VM、日志和中间离线包私有保留。生成源码/程序/镜像离线包时，使用上述官方命令，并逐项核对清单、源文件及镜像身份；旧中间包不能替代本轮最终版本。CentOS 新机、ARM 实机和新空白目标的完整离线恢复仍未验收。
