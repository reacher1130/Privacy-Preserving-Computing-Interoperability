---
status: complete
created: '2026-09-12'
tags:
  - infrastructure
  - deployment
priority: high
created_at: '2026-09-12T11:42:01.630Z'
updated_at: '2026-09-12T15:47:40.075Z'
transitions:
  - status: in-progress
    at: '2026-09-12T11:42:36.514Z'
  - status: complete
    at: '2026-09-12T15:47:40.075Z'
depends_on:
  - 002-fate-workflow-templates
completed_at: '2026-09-12T15:47:40.075Z'
completed: '2026-09-12'
---

# 家用 Linux 开发测试与可迁移演示环境

> **Status**: ✅ Complete · **Priority**: High · **Created**: 2026-09-12 · **Tags**: infrastructure, deployment

## Overview

在 192.168.31.49 同步源码、构建测试并运行开放互联平台；以环境配置区分家庭与办公网络，产物可带回办公内网部署演示。

## Design

- 家庭与办公使用单独 JSON 配置，端口和内部节点名一致。
- 源码、构建、运行数据分开；发布包只带程序、脚本和镜像，不覆盖数据库、证书、数据集或模型。
- 在新 Linux 上从源码构建前后端与适配器，运行独立原生 FATE Guest/Host；平台验收必须另查 Kuscia 与适配器证据。

## Plan

- [x] SSH、源码同步、基础依赖与隔离构建目录。
- [x] 前后端、Kuscia、FATE 适配器构建。
- [x] 原生 FATE 双节点运行与 PSI / LR 验收。
- [x] 家庭/办公配置、发布包生成与操作文档。
- [x] 用户授权后启动 Kuscia 与平台 Java 服务，启用开机自启。
- [x] 平台浏览器模板 PSI、画布 LR 与 PaddleDTX 网页训练验收。
- [x] 原生隐语任务、BFIA Python 回归与家庭合作目录初始化。
- [x] BFIA 当前 C++ 引擎构建与 Kuscia 双方执行。
- [x] 最终离线包刷新、复制到笔记本并校验。

## Test

- [x] 前端 27 项测试、TypeScript、生产构建。
- [x] 后端三节点所需两份 JAR 构建；适配器 Go 测试。
- [x] 原生 PSI `202609121207570091360`、LR `202609121208123546570` 成功。
- [x] 家庭平台 FATE 两种模板、链桨网页训练端到端验收。
- [x] BFIA 六项 C++ 算法真实通信回归、Kuscia 双方 PSI 及输出交集检查。

## Notes

操作说明位于 `NewProject/scripts/environments/README.md`。本机 Docker Hub 解析异常，使用 FATE 官方 COS 镜像包与 SecretFlow/PaddleDTX 官方国内镜像。修复旧 FATE 镜像在高文件句柄上限下的 lsof 卡住，以及默认任务申请 4 核超过分配 2 核的问题。

2026-09-12 追加：FATE 平台任务 `fj-b61d1d165db341a5`（PSI）、`fj-b8db5d62983a4e57`（LR）成功；链桨 `bfde09d0-0b77-485e-8a9d-99d598bc9441` 由网页发布并完成。修复 FATE 任务状态轮询与链桨步骤切换误提交；前端构建和 TypeScript 检查通过。

原生隐语验收 `home-native-psi-20260912223847` 成功，已检查双方输出交集。BFIA SGB/HE-WOE 在同机不同 IP 的双进程上通过实际消息收发回归。Kimi 原生后端保持不变，由网关提供只读固定模式配置以兼容共享前端。模板功能依赖 [002](../002-fate-workflow-templates/README.md)。

BFIA 当前 C++ 六项回归均通过，原生 Kuscia 任务 `home-bfia-psi-20260912233315` 成功且双方交集均为 `2、3`。修复 BFIA 目标路由就绪令牌反复重建导致的空闲高 CPU；相关 Go 回归通过，旧容器与配置保留以便回滚。18 个运行容器与 3 个后端健康检查通过，开机自启配置已确认，未重启整机。

办公部署属于回到办公网络后的后续操作，本次家庭环境验收不代表办公环境已经更新。

最终离线包 `/home/ppci/releases/20260912-153943` 已复制到笔记本 `.local-backups/home-20260912/releases/20260912-153943`，程序包与镜像包在两端的 SHA-256 一致，约 3.75 GB、18 个镜像标签。最终验收汇总在本机 `.local-backups/home-20260912/acceptance-platform/summary.json`。仅清理本次临时下载代理、本机临时构建文件与镜像；保留源码修改、当前结果、服务器构建缓存及 Kuscia 回滚副本。
