# 隐私计算开放互联平台

Alice（隐语、BFIA、FATE、PaddleDTX）、Bob（BFIA）、Kimi（隐语），包含统一前端、原生链桨管理台、FATE Guest/Host Board、算法回归和迁移打包。

## 新机器一键部署

在 **Linux + systemd** 主机执行。amd64 原生部署；arm64 自动创建 Ubuntu amd64 QEMU 虚拟机并执行相同流程（模拟运行较慢）。默认网页仅绑定本机回环地址；局域网使用下面的目标机实际地址和允许访问的网段。

```bash
git clone --recurse-submodules https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability.git
cd Privacy-Preserving-Computing-Interoperability
sudo bash deploy.sh all --host 192.168.1.100 --lan-cidr 192.168.1.0/24
```

`all` 自动安装依赖、校验源码、编译、初始化独立节点和数据库、启动服务，并运行真实公开样例。任何阶段失败会停止并返回非零状态。不要在现有办公部署上运行首次安装；脚本会拒绝接管未受本工具管理的容器/服务。

```bash
bash deploy.sh --help
bash deploy.sh sync                              # 更新当前 Git 分支和固定子模块
sudo bash deploy.sh check                        # 检查目标机依赖、目录和网络
sudo bash deploy.sh build                        # 仅构建
sudo bash deploy.sh up --no-tests                 # 部署已有构建，不运行新样例
sudo bash deploy.sh run                          # BFIA 八算法、FATE、隐语、链桨训练/预测
sudo bash deploy.sh status
sudo bash deploy.sh package --with-images --output /mnt/usb/ppci-release
bash deploy.sh package --source-only --output /tmp/ppci-source.tar.gz
bash deploy.sh clean                             # 查看可清理缓存
bash deploy.sh clean --apply
```

源码包命令也可在 macOS 使用。完整发布包需在已成功构建的 Linux amd64 环境中生成，ARM 会转交虚拟机打包并取回。详细参数、迁移、账号位置和平台边界见根目录 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 源码和数据

子模块固定到已归档的工作版本；`sync` 使用当前分支的 fast-forward 更新，不擅自升级各上游主线。FATE 的兼容修改由 `scripts/apply-source-patches.py` 幂等应用。干净 clone 同样包含经筛选的链桨历史构建源码及其校验清单，无需访问原办公目录。

部署默认隔离三个目录：仓库源码、`/opt/ppci-build` 构建产物、`/opt/ppci` 运行数据。打包只导出受控源码、程序和镜像，不复制实际数据库、私钥、上传文件、账本、模型或任务结果。上游仓库自带的公开演示身份/样本属于源码示例，不能用于生产。

本地 `privacy-computing-interconnectivity/` 有尚未合并的历史定制源码，`.local-backups/` 有原文件和验收证据，节点目录保存身份配置；它们保留原位，不纳入发布包。`clean` 仅清理明确可再生成且未被 Git 跟踪的依赖/构建缓存，保留构建必需的已跟踪 `.cache`。

## 验证记录

此前办公实机验收：[2026-11-02 恢复记录](NewProject/docs/office-recovery-20261102/README.md)、[链桨模型保存与预测](NewProject/docs/office-recovery-20261102/paddledtx-crossday-acceptance.md)、[BFIA 八算法数值和协议](NewProject/docs/bfia-eight-algorithms-numerical-protocol-20260914.md)。这些历史结果不代表新的一键部署已完成所有发行版/ARM 实机验收。当前脚本验证范围见 [部署说明](DEPLOYMENT.md)。
