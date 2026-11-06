---
status: complete
created: '2026-11-05'
tags: []
priority: medium
created_at: '2026-11-05T08:49:09.996Z'
updated_at: '2026-11-05T09:20:06.713Z'
transitions:
  - status: in-progress
    at: '2026-11-05T08:50:09.460Z'
  - status: complete
    at: '2026-11-05T09:20:06.713Z'
depends_on:
  - 003-home-linux-development
  - 010-native-counterparty-task-views
completed_at: '2026-11-05T09:20:06.713Z'
completed: '2026-11-05'
---

# 全量可迁移部署入口

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-11-05


## Overview

根目录提供独立目标机的部署、真实算法运行、程序/镜像打包和源码导出。消除办公/家庭地址、RPM路径、历史未纳Git源码和SPU历史对象依赖；清理本机可再生成内容。

承接 [003 新机运行骨架](../003-home-linux-development/README.md) 和 [010 原生追溯](../010-native-counterparty-task-views/README.md)。

## Design

- 复用现有环境脚本，源码/构建/运行状态隔离。保留既有数据，拒绝接管不受管服务/容器；不覆盖私钥或账本。
- Linux amd64原生执行；用户明确接受arm64主机使用持久化amd64 QEMU整机模拟。保留SELinux，Web绑定具体地址并限制源网段。
- 将构建必需的历史定制源码脱敏归档、记录原提交和SHA256；保留原本地集合。固定SPU构建源归档，源码包不需要Git历史。
- 包仅含受控源码、程序、镜像及可用的独立工具，不包含实际身份/业务数据。离线恢复要求目标预装系统依赖。
- BFIA使用八算法数值/通信runner，其他三平台运行真实公开样例；链桨只批准本轮文件/任务/执行器申请，不跳过健康门禁。

## Plan

- [x] 审查Git/子模块及本地缓存，保留历史定制、备份、身份和已跟踪.cache。
- [x] 根入口与跨apt/dnf依赖安装，复用全栈构建/部署与六入口网关。
- [x] 补齐链桨管理台/定制引擎、FATE双Board和BFIA页面接线。
- [x] ARM主机自动VM、来源网段规则、源码/包传输与取回。
- [x] 安全源码/程序/镜像打包、校验恢复、算法一键执行及恢复同一任务。
- [x] 根部署文档、测试及验证边界。

## Test

- [x] 自动化验证配置/目录边界、归档校验和解包安全、VM命令与状态保留、LAN限制、定向授权和预测结果。
- [x] 本机8个定制链桨程序交叉编译为Linux amd64；Python/Shell语法及现有运行状态测试。
- [ ] 目标机Ubuntu/CentOS/ARM整机首次安装、全部算法和浏览器业务验收（本次macOS无法实测，未宣称通过）。

## Notes

此规格状态表示脚本实现交付；跨系统实机验收单独保留为待验证事项。外部BaaS浏览器不属于当前四平台运行栈，旧跳转地址移除，未虚构目标集成。细节见根目录DEPLOYMENT.md。
