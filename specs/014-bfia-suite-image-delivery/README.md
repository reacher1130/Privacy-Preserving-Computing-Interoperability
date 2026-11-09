---
status: complete
created: '2026-11-09'
tags: []
priority: medium
created_at: '2026-11-09T03:39:01.236Z'
updated_at: '2026-11-09T14:50:45.716Z'
transitions:
  - status: in-progress
    at: '2026-11-09T03:39:01.463Z'
  - status: complete
    at: '2026-11-09T14:50:45.716Z'
depends_on:
  - 008-bfia-suite-in-platform
  - 011-portable-full-deployment
  - 013-core-layout-cleanup
completed_at: '2026-11-09T14:50:45.716Z'
completed: '2026-11-09'
---

# 八算法镜像交付与Kuscia一键运行

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-11-09


## Overview

承接[八算法平台入口](../008-bfia-suite-in-platform/README.md)、[免编译部署](../011-portable-full-deployment/README.md)和[核心布局](../013-core-layout-cleanup/README.md)，将公开样本验证封装为可拉取的自包含镜像，网页仍可一键取得真实结果、数值/协议校验和双方日志；新机器默认拉取已发布程序与镜像，无需编译。

程序包、suite 及全部 14 个运行镜像已公开，`releases/runtime.json` 已固定完整清单。公司浏览器八算法验收已通过；新 Ubuntu VM 的完整all连续通过（使用已验证镜像缓存及已有测试状态），正常BFIA切换后的新JAR API验收通过；新空白目标的完整离线恢复未实测。

## Design

- 用户最新约束：构建、下载大文件、容器和实测全部在公司Anolis8.10 amd64服务器，本机只编辑代码/轻量检查；允许访问服务器，保留现有服务与数据。
- suite镜像包含两项Python源码及依赖、六项C++预编译引擎、公开样本和校验器，无宿主源码挂载或容器内Docker。C++私有Debian加载器隔离其glibc与Anolis Python环境。
- Kuscia通过新AppImage/KusciaJob运行suite；固定执行器保持UUID、报告路径和后端权限接口，任务产物有界验证后落私有结果目录，保留实际执行日志。
- 镜像发布使用自有仓库固定版本和摘要；只发布干净源码构建产物，不能将现有office迁移镜像/容器提交公开，因为可能带业务数据/身份。
- 根入口默认下载固定摘要的发布清单、程序和运行镜像；build保留维护者显式编译路径，runtime bootstrap不安装编译工具。

## Plan

- [x] 自包含镜像、受控构建上下文和有界产物协议。
- [x] Kuscia任务执行器与现有网页接口接通。
- [x] 干净程序/14镜像公开发布，公开清单及20个别名的registry元数据匿名校验通过。
- [x] 新VM免编译部署与完整all入口验收（镜像缓存边界见Notes）。
- [x] 公司服务器真实八算法、日志与结果验收，记录镜像/源码/运行身份。

## Test

- [x] 镜像内无源码挂载/Docker socket执行8项，数值及协议全部通过。
- [x] Kuscia任务真实创建/结束，网页发起可刷新、查看双方日志及下载报告。
- [x] 无仓库凭据完整下载suite公开摘要，逐层SHA256及完整归档校验通过。
- [x] 新VM部署与全量运行不调用宿主Go/Maven/Node/Bazel/C++编译。
- [x] 原31个持久容器ID和已有数据保持，suite集成操作未主动重启原服务；旧执行器及配置备份已保留。另行记录的服务器重启不计作持续在线证明。
- [x] Ubuntu24.04新VM运行依赖/JRE及Docker29空库存储自动配置通过，前后无宿主编译器。

## Notes

初始只读盘点：服务器30GiB内存、约18GiB可用、116GB可用磁盘；现有Kuscia无Running任务。系统python3是3.6，已有python3.11，运行依赖必须匹配实际解释器。已有Python依赖镜像与C++镜像glibc不兼容，私有加载器方案已在临时受限容器验证，不改宿主glibc。

2026-11-09服务器实测：独立容器运行`3b90f372-498b-483d-a357-94b797fa91a1`只挂结果目录、关闭网络、只读根文件系统，8项数值/协议检查通过。Kuscia隔离运行`5daf8c4d-27af-479d-a51f-4f4a27ed8825`同样通过并回收16份双方日志；此前一次任务虽Succeeded，但集群10250日志端口未监听导致取回失败，保留失败记录。执行器改为在标准日志API不可用时，只读取已验证任务/镜像/Pod UID对应的有界CRI日志，不改集群网络或服务。上述是服务器镜像及Kuscia证据，尚不代表公开拉取、网页按钮或空白主机部署已验收。

最终suite镜像`b5288bc2…`通过公司网页同一API运行`e325aff5-d13e-4565-9eb7-010846453f4e`：8项通过、33次刷新同ID、16份双方日志与报告哈希一致；原31个业务容器ID保持，无服务重启。该次API验证最初使用local-build身份，随后公司配置已切到公开suite摘要`sha256:fa639734c9bc5b7d778c1289a2ed13ef5661a01edf2133bbb67b52e02a159d7c`。该摘要全部19层共780833522字节已匿名下载、逐层校验并通过完整crane归档验证；中断后使用Range续传，不是一次无中断冷拉取，归档摘要`0bc46dfe…`。

浏览器运行`2604c8e1…`八项数值/协议标志通过，重新加载保持同一运行，下载JSON与该运行API报告一致，SHA256为`31ac0e08b0c2b6be3c8d7fb5825683db1c98ed46d99eef1c56d670499bfa76db`；不将此运行与前次API运行的数值或报告摘要混用。

C4源码`0daa7a3`修复了CGO/SQLite构建，相关中间镜像/程序及收据保留。服务器17:38左右重启曾中断首次编译，恢复时复用既有源码与缓存续编，未重置业务数据；早期失败VM及离线包私有保留。最终公开运行版本`runtime-20261109-50f40e9`的程序包409996490字节，摘要`52f9427de3d5e41d56b60f55a9c187a7124a22f70b38846f9ecafc969e577fcc`，清单摘要`12e20f183c250d5ec0bf2080ca8fa142711fb8a8db4f855cfcc9ab08edd871cf`；既有组件仍记录实际B/C4编译来源。

Ubuntu22/24公开CI `42628281508`均通过固定提交`e6866ff`的匿名递归克隆、115项轻量检查、3项运行状态检查及runtime bootstrap/check。suite使用完整匿名归档，其他镜像因公司网络EOF而使用与公开清单一致的内容缓存，不计作一次无中断的零镜像冷拉取。无应用状态的部署及服务检查通过；首次Pending空ID的等待修复保留镜像身份/零重启要求。

业务CPP镜像`9aa7aec3…`修正入口禁用握手的问题，双节点真实握手/交集2,3通过；suite镜像保持b528。链桨SDK仅修两处XDB合约路由及旧错误构造签名，正常静态检查及真实RPC回归通过；新DAI镜像`dd243f53…`包含CGO1 executor和CGO0 requester，executor动态链接及真实SQLite DAO检查通过，两程序镜像内哈希匹配。分项链桨模型683/912B，签名读回50行、ID交集/finite检查通过，授权限定task/file/executor。

最终`4a9be60`源码/公开12e20清单原样`all --native`连续929.17秒退出0，完整匿名程序409996490B/SHA52f942通过；部署/status、八算法f172、FATE PSI/LR、SF/BFIA PSI及Paddle均通过，Paddle模型683/920B和50行预测完成，前后无宿主编译器。基线包含已核对镜像缓存与已有测试应用状态，未冒称一次零缓存冷启动。之后正常BFIA切换，新JAR029f API唯一运行5fd526cc的8项、29次同ID刷新、16日志及真实KusciaJob Succeeded通过；报告SHA21551155，不冒称新VM浏览器点击。离线打包使用官方命令，验收要求独立核对载荷、源文件及镜像身份；旧C5中间包不能作为本轮最终交付。
