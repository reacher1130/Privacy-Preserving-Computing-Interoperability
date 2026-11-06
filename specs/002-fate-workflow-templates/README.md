---
status: complete
created: '2026-09-11'
tags:
  - fate
  - frontend
priority: medium
created_at: '2026-09-11T09:40:09.642Z'
updated_at: '2026-09-12T14:46:02.329Z'
transitions:
  - status: in-progress
    at: '2026-09-11T09:40:31.419Z'
  - status: complete
    at: '2026-09-12T14:46:02.329Z'
completed_at: '2026-09-12T14:46:02.329Z'
completed: '2026-09-12'
---

# FATE 作业与画布模板

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-09-11 · **Tags**: fate, frontend

## Overview

为提交作业和可视化编排共用 PSI、PSI 与逻辑回归模板，选择数据与参与方后生成可编辑配置，验证真实 FATE 执行。

## Design

- 提交页与画布共用一套模板定义和参数生成函数，初始提供 PSI、PSI + Coordinated LR。
- 数据集按当前集群和 Guest/Host 角色筛选。仅存在一个候选时自动选择；参与方 ID 使用可修改的本地示例，训练轮数默认 2。
- 应用模板填入可编辑 JSON，或生成可编辑节点、连线及双方数据绑定；替换已有内容前提供确认。
- 验证无效 JSON、参与方、数据引用和画布依赖；修改输入框时不响应删除节点快捷键。

## Plan

- [x] 共用模板与数据绑定生成。
- [x] 作业表单与画布模板入口、适配窄屏的样式。
- [x] 构建、发布、浏览器和真实 FATE 作业验收。

## Test

- [x] 17 项 Jest 回归：模板生成、参数一致性、实例独立性、无效输入、集群/角色隔离及原有状态竞态。
- [x] TypeScript 与生产构建。
- [x] 浏览器验证模板提交与画布编排两入口、实际任务执行与成功结果。

## Notes

模板继续走现有 native-fate-v2 链路，本次不改变协议实现，不将模板功能当作 BFIA 跨平台互通验收。

2026-09-12 家庭 Linux 验收：PSI 模板平台任务 `fj-b61d1d165db341a5` 对应原生 `202609121352297100000`；画布 PSI + Coordinated LR 平台任务 `fj-b8db5d62983a4e57` 对应原生 `202609121359079384560`。平台、适配器、原生 Guest/Host 状态一致成功。活动任务列表加入五秒后台轮询；13 项模板 Jest 与 TypeScript 回归通过。证据位于家庭主机 `/var/log/ppci/acceptance-platform-20260912`。
