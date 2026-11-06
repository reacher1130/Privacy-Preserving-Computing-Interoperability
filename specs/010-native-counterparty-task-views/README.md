---
status: complete
created: '2026-11-03'
tags:
  - office
  - paddledtx
  - fate
priority: high
created_at: '2026-11-03T11:20:45.699Z'
depends_on:
  - 009-office-platform-fresh-regression
updated_at: '2026-11-03T12:22:28.972Z'
transitions:
  - status: in-progress
    at: '2026-11-03T11:20:54.503Z'
  - status: complete
    at: '2026-11-03T12:22:28.972Z'
completed_at: '2026-11-03T12:22:28.972Z'
completed: '2026-11-03'
---

# 链桨链上任务与 FATE Host 原生展示

> **Status**: ✅ Complete · **Priority**: High · **Created**: 2026-11-03 · **Tags**: office, paddledtx, fate

## Overview

在 Alice 发起端和原生对端使用同一任务 ID 核对状态与实际计算结果。

## Design

链桨原生「任务列表」提供「查询链上任务」。沿用签名认证，只允许管理员查询部署明确绑定的 Alice 请求方。从计算链按 UUID 读取摘要，不写管理库、不复制任务，不提供启动和删除。兼容现有链的 JSON 与旧 protobuf 回包。

FATE 保留 19383 Guest Board，新增只接 Host Flow 的 19384 Board。两个入口各自登录，不更改已有 Flow、任务或结果。

## Acceptance

- [x] Host Board 以独立账号实际登录，打开历史作业 `202611030824163392980` 的 Host `JG0100001100000000`，点击 `psi_0` 输出并看到 569 行。Guest Board、两侧 Flow 未重启。
- [x] Alice 网页发布公开 Boston 训练 `8ba2eca0-8538-48f8-a814-c54c5ff661b6`，原生网页按同一 UUID 查到等待审批、`executor1` 和 `executor2`。只批准精确关联的 B 方申请 `4e7d97cb-9dcc-456b-b2f2-0202e762fa74`，到北京时间 21:26:22。
- [x] Alice 的共享协议期间已切到 BFIA；使用 Alice 后端继续同一已批准任务，未再次发布、未强行切回。任务北京时间 20:13:19 完成。原生网页再次查询显示 `Finished` 与两份模型；XuperDB 签名读回与原生查询完全一致：`executor1` `4e7bb8ab-887d-431f-842b-48036fa89008`（631 字节），`executor2` `0b6a0264-8e57-49f3-8d17-7735768a196a`（908 字节）。
- [x] 原生匿名、坏签名、低权限、无效 UUID、不存在的任务均拒绝；原管理列表未新增任务。29 个受管容器健康，无错误。未执行新的预测。

## Deploy and rollback

[链桨跨环境部署](../../NewProject/docs/paddledtx-chain-task-deployment.md) · [FATE Host 接线与部署](../../NewProject/docs/office-recovery-20261102/FATEBoard.md)。

链桨办公回退与核对摘要在 `/var/backups/ppci/releases/20261103-194243-dtx-chain-task.vE4DN68a/`。该目录也含当前管理端挂载的只读配置，须保留。旧容器和旧静态入口保留，候选关闭 schema 同步。旧版两个全量签名单测的编码错误在修改前已复现；本轮有针对性的权限测试和线上签名 API 均通过。跨环境脚本尚未在第二套真实环境部署。
