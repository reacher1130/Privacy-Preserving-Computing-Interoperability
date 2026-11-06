---
status: complete
created: '2026-11-03'
tags:
  - bfia
  - office
  - acceptance
priority: high
created_at: '2026-11-03T04:31:56.089Z'
updated_at: '2026-11-03T05:46:36.935Z'
transitions:
  - status: in-progress
    at: '2026-11-03T04:32:14.609Z'
  - status: complete
    at: '2026-11-03T05:46:36.935Z'
completed_at: '2026-11-03T05:46:36.935Z'
completed: '2026-11-03'
---

# BFIA 合作节点与网页任务验收

> **Status**: ✅ Complete · **Priority**: High · **Created**: 2026-11-03 · **Tags**: bfia, office, acceptance

## Overview

区分已配置的真实对端与合作申请；修复 Alice/Bob 网页申请、确认及显示，并在办公环境验证 BFIA 与隐语公开 PSI 的网页闭环。保留既有数据及回滚备份。

## Design

合作申请使用 BFIA 管理层数据，和已配置对端、Kuscia 通信路由分开显示。只在预配置且具备签名凭据的 Alice/Bob 间交换申请和决定；收到对端确认才报告成功。不补写旧审批记录。

## Plan

- [x] 修复 BFIA 分页和本端申请、对端审批的同步。
- [x] 验证并备份、发布 Alice/Bob 共享后端及工作台前端。
- [x] 实测并记录可复现的内网网页录屏流程。

## Test

- [x] BFIA：页面显示真实已配置节点；Alice 发起新申请，Bob 看见同 ID 并批准，两边刷新状态一致。发起方不能审批，未认证跨节点请求失败。
- [x] 隐语：已有可信节点双向可用；区分新增认证和已有节点恢复。
- [x] 在真实内网页面验证切换、公开 PSI 任务提交、执行、结果预览与下载，保留两条链路的任务 ID 和结果。

## Notes

排查发现列表接口返回 `data.records` 而页面读取 `data.list`；旧申请/确认接口只写本地库。线上 Alice/Bob 各有一条旧审批，但 ID 不同。底层路由就绪不能证明已存在共同合同。

隐语工作台使用节点 ID 导航，项目审批与本地表归属使用登录机构 ID。复现：Alice 网页创建 `wckkekky`，Kimi 收到邀请但旧页面没有同意按钮；旧上传登记参数 `ownerId=alice` 返回机构/节点不匹配。保留该待审批项目用于发布后复验。

录屏样本来自仓库公开 BFIA CSV，每方六行，预期交集 ID 为 1002、1003、1004、1006。为四个节点/协议组合登记了独立命名的新表；原数据和作业未复用或覆盖。

公司内网网页实测：Alice 发出 `node-coop-5bb1450a-0efd-3573-9375-e7081f959ec8`，Bob 收到后同意，双方刷新均为已同意。原历史合同仍保留，跨节点未签名请求返回 403。

Kimi 旧关联：Alice 节点绑定历史机构 `owszmazx`，新邀请用实际机构 `rqzvglmu`。经 44 表记录比对，在线备份后只补入权威机构并改一处节点机构引用，旧机构与完成投票保持原状。Kimi 网页同意原项目 `wckkekky` 后，两端项目均为 APPROVED；新公开表已绑定到画布 `yoyytwos`。

BFIA 网页闭环：项目 `c07d476919db43b992a5f6f79f0b3bee`、流程 `ucplzxzq`，Alice 和 Bob 从各自网页完成项目/流程审批。Alice 网页点击执行生成 `srbm`，两端同一画布都能打开输出预览并下载实际 CSV。交集均为 1002、1003、1004、1006；Alice 仅含 `id,age,income`，Bob 仅含 `id,score,label`。Bob 的结果入口在该已审批画布，未扩展为任意算法或全局结果历史。

发布证据：后端 V2 524 项用例、0 失败、1 项可选 FATE 探测跳过；前端 V4 生产构建、TypeScript、36 项测试通过。两次后端发布均各有 22 文件数据库冷备，前端备份为完整目录。回滚记录保存在服务器 `/var/backups/ppci/releases/20261103-125745-bfia-workflow-v1.6yj6ix1m`、`20261103-130642-bfia-peer-result-v2.sk74869h`、`20261103-130915-frontend`；机构在线备份在 `/var/backups/ppci/native-kimi-alice-institution`。

隐语首个网页作业 `zbza` 保留为 Failed：两端 PAD 原先写入各自宿主机上传目录，计算端在 Kuscia 持久挂载中找不到对应 CSV。已通过现有挂载共用本地数据目录，仅恢复缺失的公开样例文件，原目录未改名或删除。Alice/Kimi 原生上传和 Alice BFIA 上传的新样本均已从各自容器逐字节读回。目录和启动配置回滚备份：`/var/backups/ppci/releases/20261103-132518-native-shared-storage.c3s_qvs0`。

修复目录后，在 Alice 原画布网页执行的新作业 `mtwx`，Alice/Kimi 均为 SUCCEED。原结果同步只从 Kimi 的 Kuscia 查询，导致 Alice 本方真实结果未进成果列表；核验实际产物后只补录一行结果索引，48 张表的旧记录不变。随后两端「计算成果」均可下载同一作业 `mtwx-new-n3-output-0`，校验四个预期 ID 和各自本地列。在线备份在 `/var/backups/ppci/native-alice-mtwx-result`。

最终后端 V3 只补查属于本节点的真实联邦结果表；Maven 525 项，0 失败、1 项可选探测跳过。发布后从 Alice 原画布网页新建作业 `klao`，3 个节点全部成功；无需手工写库，Alice 与 Kimi 的成果页各自自动出现 `klao-new-n3-output-0`，两份实际网页下载的 CSV 都是同样四个 ID，且各方只有本方列。V3 的 22 文件冷备与 V2 JAR 在 `/var/backups/ppci/releases/20261103-134314-native-result-v3.sjg68vzq`。

## 录屏顺序

1. [Alice](http://192.168.45.101:18101/edge?ownerId=alice) 切到 BFIA，进入协作伙伴；[Bob](http://192.168.45.101:28101/edge?ownerId=bob&tab=connectivity-connected-node) 反向查看。要录新增审批，选择已配置的 Bob 并设置一个新的未来有效期，再由 Bob 同意；只展示结果可直接使用同 ID 的既有记录。
2. BFIA 项目 `record-bfia-20261103-01` → 流程 `record-bfia-psi-20261103` → 悬停 ECDH 隐私求交 → 输出表 `psi_out`。两端分别展示 `srbm` 的四行本方数据，点击「下载结果 CSV」。
3. 切回隐语，[Kimi](http://192.168.45.101:38101/edge?ownerId=kimi) 协作伙伴显示 Alice 可用；打开 `record-native-20261103-01`，展示原邀请通过和 `record-native-psi-20261103` 画布。[Alice 成果页](http://192.168.45.101:18101/edge?ownerId=alice&tab=result)和 [Kimi 成果页](http://192.168.45.101:38101/edge?ownerId=kimi&tab=result)各自查找 `klao-new-n3-output-0` 并下载。
