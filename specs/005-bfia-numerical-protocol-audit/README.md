---
status: complete
created: '2026-09-14'
tags: []
priority: medium
created_at: '2026-09-14T03:39:58.048Z'
updated_at: '2026-09-14T04:54:49.951Z'
transitions:
  - status: in-progress
    at: '2026-09-14T03:42:44.872Z'
  - status: complete
    at: '2026-09-14T04:54:49.951Z'
depends_on:
  - 004-office-home-release-sync
completed_at: '2026-09-14T04:54:49.951Z'
completed: '2026-09-14'
---

# BFIA 八算法数值与协议日志验收

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-09-14


## Overview

承接 [004](../004-office-home-release-sync/README.md)，核实链桨合约来源，修复八算法数值问题，提供能对照实际 BFIA v2 握手和计算流程的双边详细日志。

## Design

独立工作树 `.local-backups/bfia-audit-work`，分支 `codex/bfia-numerics-20260914`；不修改已部署基线。以仓库 interconnection v2 protobuf 为协议依据，区分本实现双方互通、数值参考验证与第三方平台互操作认证。日志不输出私钥、令牌或原始私有数据。

## Plan

- [x] 查明现有合约属于 shared-exchange-Connectivity 联通定制合并 paddlempc；与官方 fLTask 类型不同。
- [x] 定位 LR 定点下溢、份额浮点精度丢失、VIF 单位矩阵与归一化、XGB 单树及本地特征预测缺陷。
- [x] 独立构建数值修复候选，运行双方公开数据与明文参考对照。
- [x] 八算法结构化阶段/握手/消息元数据/输出日志与自动流程检查。
- [x] 回归异常握手和结果语义，部署已通过验证的候选并归档证据。

## Test

精确环份额先模加重构再定点解码；PSI 与比较精确相等；Pearson/VIF 与 NumPy 对照；LR/XGB 与相同参数明文计算对照。日志阶段必须来自实际执行点，不由测试脚本伪造。

## Notes

公司合约证据：NewProject/docs/paddledtx-unicom-local-deployment-20260905.md；运行镜像 ppci-migration/xchain1-node-com:20260908，容器 paddlempc SHA256 bbb0d34b6593a6d4df8370f5db6b61394f07911fcee237f592580eb19f71018e。部署记录与接口行为对应定制源码，二进制未携带可直接映射的 Git commit，不能声称字节级可复现溯源。

验收详情：`NewProject/docs/bfia-eight-algorithms-numerical-protocol-20260914.md`。八算法办公入口数值/流程通过；多轮训练、指定接收方及握手拒绝通过。最终镜像 `ppci/bfia-cpp:numerics-20260914-v2`，原文件回滚备份 `/var/backups/ppci/bfia-numerics-20260914`。完整日志保存在服务器；下载本机受自动审批限制，待明确批准。
