# 链桨模型保存与预测验收（2026-11-03）

两项均通过。公司服务器 `192.168.45.101` 恢复 SSH 和网页访问后，两侧 XuperDB `paddlempc` 均有 2 个合格节点，达到 2 副本要求。storage1/2 在线且为 Yellow，过去七个完整日各有 189 次真实心跳；storage3 在线但仍为 Red。未改评分、节点身份、存储类型或门禁。

在 Alice 实际内网页面提交纵向线性回归训练和预测。每次发布都返回任务 ID，刷新仍能找回同一条待审批记录；A 方自动确认，只批准与本次任务和对应公开 B 文件绑定的申请，各限时两小时以内。两个任务都从网页继续原 ID，没有重复发布。时间均为北京时间。

| 步骤 | 真实结果 |
| --- | --- |
| [训练](http://192.168.45.101:18101/edge?ownerId=alice&tab=paddledtx-results&taskId=7c442cd7-2d64-4dd7-98ec-5a0a2df700d7) | 独立公开 Boston A/B 各 456 行，B 方目标列 `MEDV`。任务 `7c442cd7-2d64-4dd7-98ec-5a0a2df700d7` 于 09:32:32 `Finished`，无错误。 |
| 模型保存与读回 | 两侧真实 `paddlempc` 分别存入 631 字节和 912 字节的非空模型。每份按文件 ID、按训练 ID 命名，以及用对应执行器身份读取，字节与 SHA256 一致。 |
| [预测](http://192.168.45.101:18101/edge?ownerId=alice&tab=paddledtx-results&taskId=6a7fd227-7525-4c63-ba11-f56c530951a2) | 任务 `6a7fd227-7525-4c63-ba11-f56c530951a2` 使用上述训练 ID 和独立的公开 50 行输入，于 09:54:12 `Finished`，无错误。 |
| 结果核验 | 现有 requester 签名 RPC 从真实执行器读回 `id,value` CSV（1,080 字节、50 行）。50 个唯一 ID 与两份预测输入的交集完全一致，所有预测值有限。 |
| 终态幂等 | 对已完成的本轮预测调用一次 `start`，返回原任务快照，未调用启动 CLI；前后任务 ID 集合和任务状态、时间均相同。 |

模型文件 ID 分别为 `9d5f10f5-5fc9-40cb-abbe-1126dcc89fd8`（executor1）与 `d268ae35-455b-429b-bfb7-dfb5643b92a3`（executor2）。旧辅助 `xdb-cli` 会把合法模型 JSON 误报为空错误码。临时诊断客户端复用现有源码及原签名身份，既能读回两个模型，也会拒绝真实的文件不存在错误 `10004`；核对现运行的两份执行器二进制均已有空错误码保护。生产预测通过，没有替换旧辅助 CLI 或任何运行组件。

重启后 29 个受管容器、3 个后端及两侧存储均通过状态检查。24 个任务恰为原 22 个加本轮两条，原 `7c9f47bd-65f3-4a61-874d-c5dc8ba7c5ac` 仍为 `Failed`，快照不变。Alice 恢复备份的哈希和完整性复核通过。四份新样本放在独立命名空间，未覆盖旧文件、模型、数据库或回滚材料。

本轮公开摘要：

- [重启后的平台与保留核验](evidence/post-boot-20261103-platform-preservation.json)
- [两侧模型读回](evidence/20261103-acceptance/paddle-model-readback.json)
- [预测输出与网页操作](evidence/20261103-acceptance/paddle-prediction-result.json)
- [原任务和运行二进制保留核验](evidence/20261103-acceptance/paddle-task-preservation.json)

原始模型、CSV 和授权证据保留在服务器。服务器证据目录为 `/var/log/ppci/regression-20261102/20261103-acceptance/`。自动审批因完整授权日志可能含组织或授权信息，拦截了日志回传；未绕过，Git 只纳入验收摘要。浏览器截图保存在本机 `.local-backups/office-recovery-20261102/screenshots/`。

本次验证公开样本下的真实训练、持久化和预测链路，不评价生产数据上的模型精度。
