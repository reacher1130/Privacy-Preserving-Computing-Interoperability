---
status: complete
created: '2026-09-14'
tags: []
priority: medium
created_at: '2026-09-14T02:55:06.380Z'
updated_at: '2026-09-14T03:36:12.574Z'
transitions:
  - status: in-progress
    at: '2026-09-14T02:55:22.160Z'
  - status: complete
    at: '2026-09-14T03:36:12.574Z'
depends_on:
  - 003-home-linux-development
completed_at: '2026-09-14T03:36:12.574Z'
completed: '2026-09-14'
---

# 家庭已验收版本同步到办公环境

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-09-14


## Overview

承接 [003](../003-home-linux-development/README.md)，将家庭环境的前端、Kuscia 修复和离线产物同步到办公服务器 192.168.45.101:2222。

## Design

以已校验的家庭发布包 20260912-153943 和对应本地源码增量为依据；保留办公数据库、证书、挂载、节点身份和旧容器。源码同步逐文件比对基线，不覆盖独立修改。不重新初始化已有节点。

## Plan

- [x] 核对家庭验收证据、办公基线、离线包 SHA256。
- [x] 暂存发布包、备份并同步源码增量。
- [x] 发布前后端、升级 Kuscia 和计算镜像，保留可恢复旧版本。
- [x] 健康、浏览器、真实任务验收并记录缺口。

## Test

核对部署文件哈希及镜像；验证 FATE 模板/画布、链桨向导、隐语与 BFIA 双方 PSI。八算法数值缺口独立记录，不把通信 PASS 当数值正确。

## 2026-09-14 办公环境交付记录

迁移范围已完成，链桨底层兼容例外及既有数值问题列于下方。入口：http://192.168.45.101:18101/edge?ownerId=alice 。SSH 为 root@192.168.45.101:2222。

### 已部署与校验

- 家庭发布包 `20260912-153943` 完整传入 `/opt/ppci-releases/home-20260912-153943`，两份归档 SHA256 均一致。
- 28 个源码增量同步到 `/opt/ppci-source`，逐文件 SHA256 一致；保留本地未提交修改，未做 Git 提交或推送。
- 202 个前端文件、SecretPad 与 Kimi 两个 JAR 均与家庭离线产物一致，已部署至 `/opt/ppci/NewProject`。
- 18 个镜像标签的 config 内容与 RootFS 层均与归档一致。家庭 Docker 29 的 OCI manifest ID 与办公 Docker 26 config ID 语义不同，不能直接比较这两种 ID。
- Alice/Bob/Kimi Kuscia 逐个升级为家庭镜像，原 IP、挂载、数据库和证书保留；计算镜像按角色导入内部 containerd。
- 最终 `ppci-platform status` 为 `healthy=true`、`errors=[]`；旧三个 Kuscia 容器均停止且 restart=no。

### 真实执行证据

| 验收 | 标识 | 结果 |
| --- | --- | --- |
| FATE 模板 PSI | fj-177f798546a94f22 / 202609140303078472380 | 浏览器 SUCCESS，原生双端执行成功 |
| FATE 画布 PSI+LR | fj-51f5ba3d07374a50 / 202609140306193770070 | 浏览器自动刷新 SUCCESS，画布生成配置可编辑 |
| Kuscia 升级后 FATE PSI | fj-f86acfa6690f46f7 | 浏览器 SUCCESS |
| 链桨已授权公开数据训练 | 1346e6e8-1f1a-435e-ac47-80ecc0180060 | 浏览器三步提交、引擎 Finished、反馈页已完成，两个模型结果 ID |
| BFIA Alice/Bob PSI | office-bfia-psi-20260914112445 | Succeeded，双方输出均为 ID 2、3 |
| 隐语 Alice/Kimi PSI | office-native-psi-20260914112606 | Succeeded，双方输出均为 ID 2、3 |
| BFIA 八算法回归 | office-home-release-20260914 | Python 2 项、C++ 6 项 PASS，退出码 0；这是通信/执行验收 |

前端验证还包括：Guest ID 填 Alice 时正确提示不能用节点名；链桨前两步不会提前提交。截图人工检查通过。浏览器任务归档含三条同一时刻的历史 SyntaxError 警告，未据此宣称控制台零错误；以上实际任务闭环均成功。

### 兼容例外和未解决问题

1. 办公链桨采用既有分支合约，数据元信息为数组，PublishFLTaskOptions 的 fLTask 序列化也不同于家庭 stock 版本。家庭 requester 直接替换后不兼容，已恢复原二进制及配置并校验哈希；链账本、合约、数据卷未升级。家庭二进制保留在发布目录。前端向导与已授权训练可在此兼容组合下工作，因此不能表述为链桨底层全量版本统一。
2. 首次使用未授权公开数据时，前端请求超时后不能保留待续任务记录。任务 e7939a70-354f-4ea9-9160-d12e3219afef 经批准对应数据访问并启动同一个任务后 Finished；没有重复提交该任务。随后独立的已授权验收任务完整走通浏览器闭环。长时间审批后的任务恢复仍是产品缺口。
3. 八算法 PASS 不代表数值正确。既有 SS-LR 零参数、SS-XGB 双方结果差异、Pearson/VIF 份额还原与精度问题未在本次迁移中修复。迁移前控制实验及输出位于本地 `.local-backups/bfia-output-demo/office-output-20260914-103456`，迁移后原始回归产物保留在服务器 `/opt/ppci-source/NewProject/secretflow/bfia/results/{python,cpp}/office-home-release-20260914`。

### 证据与恢复入口

本地证据目录：`.local-backups/office-sync-20260914/evidence/`，包含文件核验、镜像核验、健康摘要、FATE 与链桨响应、BFIA/隐语日志、浏览器截图。服务器完整记录：`/var/backups/ppci/home-sync-20260914`。没有将包含密钥的容器配置或备份数据库下载到证据目录。

- 前端旧版：`/var/backups/ppci/releases/20260914-105903-frontend/dist`
- Alice/Bob 后端旧版：`/var/backups/ppci/releases/20260914-105928-backend/secretpad.jar`
- Kimi 后端旧版：`/var/backups/ppci/releases/20260914-110004-kimi/secretpad.jar`
- 源码原文件：`/var/backups/ppci/home-sync-20260914/source`
- Kuscia 旧容器：`gaofeng-kuscia-autonomy-{alice,bob,kimi}-before-home-20260914`；逐节点配置、状态归档在同名角色目录。回退前须停止新容器，并按记录恢复网络/IP、名称与原重启策略；不得同时启动新旧节点。未执行破坏性的整环境回退演练。
- 原镜像另有 `ppci/rollback-home-sync:20260914-*` 标签，映射见 `image-tags-before.json`。
