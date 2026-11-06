# 全量部署、算法运行与迁移

根目录 `deploy.sh` 是统一入口。目标是独立开发/演示环境；复用既有业务库、链或办公节点的升级，应沿用相应备份/升级流程。

## 系统和资源

| 主机 | 执行方式 | 验证边界 |
| --- | --- | --- |
| Ubuntu 22.04/24.04、Debian，amd64 | apt 安装系统依赖，隔离工具链，Docker + systemd | 已编写部署路径，未逐发行版实机验收 |
| CentOS Stream 9/10、兼容的 RHEL/Rocky/Alma/Anolis，amd64 | dnf；Java/Node/Go/Maven 使用独立目录；保留 SELinux | 仓库已有 Anolis 历史运行证据；新入口未逐系统实测 |
| 上述 Linux arm64/aarch64 | Ubuntu amd64 cloud image + QEMU TCG 整机模拟 | 已做配置/命令/安全边界测试，未做 ARM 实机部署验收；明显慢于原生 |
| macOS | 本地缓存清理、完整源码导出 | 不在 macOS 原生安装 Linux 服务 |
| CentOS 7/8 等已停止维护系统、32 位 ARM、其他 CPU | 不承诺自动安装；先准备受支持的 Linux 主机/虚拟机 | 不把架构检测通过视为全栈兼容 |

建议至少 8 个逻辑核、24GB 内存、100GB 可用磁盘；ARM 宿主机还需给模拟 VM 预留资源。默认 VM 分配 4 vCPU、16GB 内存。首次编译和拉镜像需要网络；下载失败会退出，可以处理网络后重试。旧系统缺 Python3.9+ 时应先升级运行宿主。

## 一键执行及拆分阶段

```bash
sudo bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

将 IP/CIDR 改为目标机器实际地址和允许访问的内网。无参数时默认 `all`，网页仅开放 `127.0.0.1`。安装器安装 Docker、nginx、系统包和独立工具链，启用对应服务；不卸载已有 Docker，不删除已有卷，不关闭 SELinux/防火墙。与现有环境冲突时停止，避免把已有环境当作空机器。

`--no-tests` 只跳过部署后的新样例执行，仍进行构建及健康检查。`up` 使用已有构建/镜像；`build` 不发布；`sync` 拉取当前 Git 分支并同步固定子模块。源码包没有 `.git` 时，`sync` 只验证源码清单。

源码、构建目录、运行目录不能互相包含。默认使用当前仓库、`/opt/ppci-build`、`/opt/ppci`；可用 `PPCI_BUILD_ROOT` / `PPCI_ROOT` 设置独立绝对路径：

```bash
sudo env PPCI_BUILD_ROOT=/data/ppci-build PPCI_ROOT=/data/ppci \
  bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

内部 Docker 网络为 `192.168.117.0/24` 和 `172.31.1.0/24`。目标网段冲突必须先解决。VM 内使用私有 NAT，外部网页端口映射到宿主机；非回环映射由专用 iptables 规则限制来源 CIDR，不刷新其他防火墙规则。

## 全量覆盖和入口

| 内容 | 入口/行为 |
| --- | --- |
| Alice 统一平台 | `http://目标机IP:18101`；隐语、BFIA、FATE、PaddleDTX |
| Bob / Kimi | `http://目标机IP:28101` / `http://目标机IP:38101` |
| FATE Guest / Host Board | `http://目标机IP:19383` / `http://目标机IP:19384`；独立会话和目标机生成的账号 |
| 链桨原生管理台 | `http://目标机IP:18511/dtx/console/`；签名登录、管理库、上传/下载、只读链上 UUID 查询 |
| BFIA | 当前 C++ 引擎、七个组件镜像别名、Python 引擎、合作目录、统一平台八算法中心 |
| 原生隐语 | Alice/Kimi Kuscia、SecretFlow 计算镜像、公开 PSI 样例 |
| FATE | 双 Flow、字符串 party ID 兼容、适配器与 Kuscia AppImage、双 Board |
| PaddleDTX | 三链、三个数据拥有方、三个存储、三个执行器、定制计算/管理合约、MySQL、原生管理台 |

目标机生成的凭据只保存在目标私有目录：链桨为 `/opt/ppci/native/dtx-manager/private/credentials.json`，FATE 为 `/opt/ppci/fateboard/{guest,host}/credentials.properties`。自定义 `PPCI_ROOT` 时路径随之变化。不要把这些文件加入 Git 或发布包。统一平台沿用各模块自身的账号初始化规则。

这是公开样例的独立演示链，包含上游公开测试身份/合约账号。不要用于真实机构或资产。新部署使用 Local 模型/预测持久卷；既有 XuperDB 数据和模型不包含在程序包中。部署显式关闭健康跳过参数，不改写心跳评分、不绕过存储门禁。新节点尚不满足健康条件时，相关样例会失败，需要待节点就绪后重跑。外部 BaaS 区块浏览器不属于当前四平台运行栈，需要另配目标服务，不能沿用历史外部地址。

## 算法一键运行

```bash
sudo bash deploy.sh run
```

依次运行：BFIA 的 SGB、HE-WOE、ECDH-PSI、SS-LR、SS-XGB、SS-Pearson、SS-VIF、SS-Compare；FATE PSI 和 PSI+联合逻辑回归；隐语 Alice/Kimi PSI；BFIA Alice/Bob Kuscia PSI；链桨公开 Boston 纵向线性训练、模型读回和预测。BFIA 使用带数值/通信检查的 runner。任一失败返回非零状态。

链桨只批准**本轮 task UUID + 本轮文件 + 对应执行器公钥**的公开样例申请，有效期两小时，保留其他申请；核对双方非空本地模型、预测 ID 交集/唯一性及有限数值。摘要写在 `/var/log/ppci/paddle-smoke-*`。超时后用原输出目录恢复同一任务：

```bash
sudo python3 scripts/paddle-smoke.py --output /var/log/ppci/paddle-smoke-实际目录
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

在已成功构建全栈的 Linux 环境生成程序/镜像发布包：

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

本机清理约 1GB 已忽略依赖/构建缓存，保留历史定制集合、备份、节点身份和已跟踪的 Bazel 覆盖源码；同步当前工作分支及固定子模块。47 项部署/打包/VM/授权自动化测试和既有 3 项运行状态测试通过；完整源码包已实际生成、解包、验证清单，并在无 `.git` 的导出副本中运行测试。8 个定制链桨 Go 程序完成 Linux amd64 交叉编译；管理端安全回归、元数据兼容及原生前端测试和生产构建通过。

本次工作机为 macOS，未在新 Ubuntu/CentOS/ARM 整机执行 `all`，未下载全套镜像或生成已验收的运行镜像包，也未触发办公任务。以目标机真实退出状态、任务输出和浏览器验收为准。
