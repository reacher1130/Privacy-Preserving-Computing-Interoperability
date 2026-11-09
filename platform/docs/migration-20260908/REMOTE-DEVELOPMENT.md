# 服务器开发、部署与运维

2026-11-02 更新：办公已验收修复已归档到 Git；新增链桨管理后台后，当前项目管理范围为 29 个容器和 3 个后端。最新变更、验证边界和回退位置见 [办公恢复记录](../office-recovery-20261102/README.md)。下方 2026-09 记录保留为历史证据。

连接：`ssh -p 2222 root@192.168.45.101`。本文不保存登录密码。

| 位置 | 用途 |
| --- | --- |
| `/opt/ppci` | 互联互通项目源码、部署配置和当前发布产物 |
| `/opt/ppci/NewProject/secretflow` | BFIA 八算法源码与测试 |
| `/opt/ppci-build` | 后端、Kimi、前端的独立编译工作区及 Maven 缓存 |
| `/opt/ppci-tools` | 项目使用的 Java 构建工具、Node 20、pnpm 8、Go、ripgrep 等 |
| `/srv/ppci` | Kuscia 持久化数据、部分数据库；其他数据库仍在对应 SecretPad 目录 |
| `/var/backups/ppci` | 迁移归档、原本地数据、发布回退文件 |
| `/var/log/ppci` | 三个后端、编译及验收日志 |

本项目的 28 个常驻容器和 3 个 Java 后端在服务器运行。Alice 支持四协议，Bob 仅 BFIA，Kimi 使用原生隐语；FATE Guest/Host 独立部署。算法任务和测试的临时计算容器也在服务器创建。本地无需 Docker、Python 算法环境或 Java 服务运行。

## 常用命令（登录服务器后执行）

```bash
ppci-platform status
ppci-algorithms all       # SGB、HE-WOE + 六项 C++ BFIA 通信测试
ppci-algorithms python
ppci-algorithms cpp
ppci-algorithms build-cpp # Bazel 编译并构建精简运行镜像

ppci-build backend       # Alice/Bob 共享后端
ppci-build kimi          # Kimi 原生后端
ppci-build frontend      # 统一演示前端，Node 20 + pnpm 8

ppci-deploy backend
ppci-deploy kimi
ppci-deploy frontend

ppci-platform restart    # 仅重启本项目的 28 容器和 3 后端
```

`ppci-build` 输出到独立目录，不覆盖运行版本；Java 构建使用 `-DskipTests`，编译成功不代表全量 Java 单测通过。`ppci-deploy` 备份旧产物，切换后执行健康检查，失败时恢复旧产物。前端发布保留旧哈希资源，避免已打开页面失效。原生 Kimi 前端、FATEBoard、PaddleDTX 前端是独立发布物，不由统一前端命令覆盖。

测试日志与每个参与方的收发证据保存在 `/opt/ppci/NewProject/secretflow/bfia/results/`。C++ 测试使用精简镜像内部二进制，不依赖本地挂载的编译文件。Python 测试使用 `ppci/bfia-python:amd64-20260908`；构建配方为 `NewProject/scripts/linux-migration/Dockerfile.bfia-python`，实际依赖见 `bfia/requirements-linux-tested.txt`。

## 源码修改

可以在本地编辑源码，通过 SSH/SCP 将明确修改的源文件同步到 `/opt/ppci` 的对应相对路径，再在服务器执行构建与发布。不要将整个本地目录覆盖到服务器运行目录：服务器中的数据库、证书、协议状态及 Linux 启动配置需要保留。构建、安装依赖、镜像制作和运行均在服务器完成。

保留本地各 Git 仓库、源码、锁文件、配置、文档和手写补丁。`secretflow/interconnection-impl/.cache` 下的手写补丁脚本与 `overridden` 目录属于构建输入，不能按普通缓存整体删除；可重建的 Bazel 缓存和下载归档单独清理。共享的系统级开发工具及其他项目资源不属于本次清理范围。

## FATE 重启稳定性

原生 OSX 联邦路由必须使用 `fate2-flow-guest-e2e`、`fate2-flow-host-e2e` 这两个 Docker 名称，不能保存动态容器 IP。`configure_native_fate.py` 写入稳定路由，健康检查同时校验路由，防止 HTTP 页面正常但跨节点任务失败。

## 验收范围

迁移验收包括八算法真实通信、HE-WOE 新增单元测试，以及四协议代表性计算任务。此范围不等同于 SecretFlow 上游全部 pytest 或整个项目所有功能测试。PaddleDTX 原生管理控制台 `/dtx/v1/` 的历史管理后端接线缺口仍需单独开发；统一平台的 PaddleDTX 真实计算链路单独验收。

## 2026-09-08 源码重建后验收

Alice/Bob 后端、Kimi 后端和统一前端均在服务器从源码构建、发布成功，发布后的 28 容器、3 后端和协议拓扑健康检查无错误。Java 构建跳过单测，未据此宣称 Java 全量单测通过。

| 验收项 | 记录 | 结果 |
| --- | --- | --- |
| BFIA Alice/Bob PSI | `rmhl` | 三个节点 SUCCEED |
| 原生隐语 Alice/Kimi PSI | `shkm` | 三个节点 SUCCEED |
| PaddleDTX 预测 | `977f0939-eafa-49de-8973-938c8b0f594f` | Finished |
| FATE 修复稳定名称路由 | `fj-e8abfbea83284df5` | SUCCESS |
| FATE 重启与 IP 互换回归 | `fj-75e4d362751e4e5a`，原生 `202609081046293133280` | Guest、Host、Arbiter 全部 success |
| 八算法迁移镜像通信 | `remote-20260908-180906` | Python 2/2、C++ 6/6 |
| HE-WOE 单元测试 | `/var/log/ppci/bfia-unit-tests.log` | 4 passed |

FATE 重启前 Guest/Host 分别为 `10.240.0.3`、`10.240.0.4`，重启后互换；新任务仍完成 PSI 和两轮联合逻辑回归。证据见 `fate-restart-addresses.txt`、`fate-restart-*-query.json`。Alice 最终恢复为隐语协议，仍提供四协议切换；Bob 的后端配置仅支持 BFIA，Kimi 使用原生隐语页面。

后端构建日志为 `backend-build.log`、`kimi-build.log`，前端为 `frontend-build-v3.log`，均在 `/var/log/ppci`。旧发布物位于 `/var/backups/ppci/releases`，本地最后一份运行数据归档为 `/var/backups/ppci/migration-20260908/local-final-state.tar.gz`，附 SHA256 和文件清单。

## 2026-09-09 完成记录与 Git 同步

- C++ 源码完整构建通过：`/var/log/ppci/bfia-cpp-build-v6.log`。
- 新精简镜像 `92f590480604`，167,610,612 字节；六算法测试 `source-rebuild-20260909` 全部通过。
- lib25519 专项测试通过：`/var/log/ppci/bfia-lib25519-tests-v2.log`。
- 本地 Bazel 生成缓存已清理，手写补丁及覆盖源码已保留并纳入 Git。
- 修复重启后的 IP 冲突：五个代理固定为 `192.168.117.10` 到 `.14`；Alice/Bob/Kimi 仍为 `.2`、`.3`、`.4`。节点恢复后健康检查无错误。
- 前端静态检查实际失败：23 个 ESLint 错误、162 个警告及格式问题；日志为 `/var/log/ppci/frontend-source-lint.log`。提交钩子依赖不在本地安装，服务器检查结果按实记录；本次只归档已有实现，不将静态检查标为通过。

源码总入口：`https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability`（私有）。服务器 Git 工作区使用 `/opt/ppci-source`，运行目录继续使用 `/opt/ppci`。源码同步后执行补丁脚本，再编译、发布。`ppci-build` 默认从源码工作区构建；算法命令将 SecretFlow/YACL 源码同步到已有 Linux 缓存旁，保留算法结果和缓存。

本地编辑子模块后，需要先提交并推送子模块，再在总入口提交更新后的子模块版本。服务器只拉取固定版本，不直接在运行目录执行 Git pull。历史 BaaS/dtx 等集合未发布。FATE 使用固定公开上游版本和已审查补丁，避免整目录上传。

### GitHub 同步后的实际验收

2026-09-09 已从 GitHub 完整拉取 10 个顶层模块并校验固定版本；FATE 五个源码文件补丁成功应用。后端在新的 Git 工作区重新编译、发布成功，28 容器与 3 后端健康检查无错误。Python 两项与 C++ 六项通信测试分别通过；记录见 `git-source-verification.json`，完整日志保留在服务器。

C++ 测试默认自动生成固定种子的合成 CSV，不依赖被 Git 忽略的旧数据文件。源码同步保护算法数据目录，并在任何删除同步前校验关键源码文件，防止不完整检出被当作有效源码。旧 C++ 样例 CSV 的服务器副本补传待用户明确批准，本地原文件保留。

常用命令均指向 Git 源码工作区中的脚本。服务器使用仓库专用只读部署密钥，不保存个人 GitHub Token。已有目录中的凭据内嵌 Git URL 已移除。FATE 应用补丁后显示工作区修改是预期状态；不要使用强制重置来清掉这些修改，统一使用 `scripts/sync-source.sh` 重新同步与应用补丁。
