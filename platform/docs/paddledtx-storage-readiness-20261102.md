# 链桨存储信誉与跨日验收（2026-11-02）

## 当前真实结论

办公任务 `7c9f47bd-65f3-4a61-874d-c5dc8ba7c5ac` 经网页发布、刷新找回、文件授权确认及同 ID 网页继续执行后，在模型保存阶段变为 `Failed`：`failed to save task model -> empty healthy nodes`，结果为 `map[]`。保留该失败任务和现存产物；未改状态、未重发或以重建容器代替恢复。

2026-11-02 18:16 中国时间实查：三个正式 storage 均 Online，健康 API 业务码均为 `0`，颜色均为 Red；健康历史窗心跳均为 `0/10080`。今日真实分钟心跳 storage1/2 为 `107`、storage3 为 `83`，节点更新时间距检查不足 30 秒。18:23 再查近 15 分钟心跳错误均为 0，主机与容器时钟一致、存储目录可写、磁盘仍有约 132 GiB 可用空间。

当前及下一健康窗的 proved/failed/toprove 挑战数均为 0。现有证据支持长期停机后的历史信誉惩罚，不支持心跳服务故障、时钟错桶、命名空间丢失或配置身份错误。

## 原规则与最早恢复条件

定制 XDB 的节点评分为：

    score = 0.7 × 挑战成功率 + 0.3 × 历史心跳率

无挑战记录时挑战成功率使用既有基线 `0.85`。老注册节点只统计此前七个已完成日期的心跳，固定分母 `10080 = 7 × 1440`；今日新心跳不进入当前评分。当前分数因此为 `0.7 × 0.85 = 0.595`，低于 Yellow 下界 `0.6`。

在挑战基线不变时，达到 Yellow 所需的真实历史心跳为：

    0.595 + 0.3 × (heartbeats / 10080) >= 0.6
    heartbeats >= 168

`167` 次仍低于阈值，`168` 次恰达 Yellow。2026-11-02 的真实心跳最早在 **2026-11-03 00:00（中国时间，UTC+8）** 的日期窗口轮转后计入。模型命名空间副本数为 `2`，故至少两个节点各满足所需信誉、Online 且健康为 Green/Yellow 后才具备节点数量条件；不是所有容器 Running 就可写。

此时间是条件性最早边界，不是成功保证。必须保持原节点正常产生真实分钟心跳，并于跨日后重新读取实际健康。没有伪造历史、突发刷心跳、重注册原身份、创建新身份绕过信誉、降低阈值、跳健康检查或切换模型为 Local 存储。

## 模型实际接线与只读检查

两个 executor 的有效字段均为 `modelStorageType = "XuperDB"`，分别写入 `http://dataowner1.node.com:80` 与 `http://dataowner2.node.com:80` 的 `paddlempc` 命名空间。另一个旧字段 `type = 'Local'` 不是当前模型存储开关。

两个 dataowner 的命名空间查询均返回业务码 `0`，`namespace.replica = 2`。省略 owner 时使用 dataowner 自身身份；executor 的 `ukeys` 是白名单客户端签名身份，不是命名空间 owner。两组 ukeys 的私钥派生公钥与已存 public 文件一致；将 uploader public key 错当 namespace owner 查询会得到 `10004`，不能据此认定真实命名空间不存在。

主机现成只读 API（无私钥或 token）：

| 目的 | 请求与校验 |
| --- | --- |
| 正式 storage 列表 | `GET http://127.0.0.1:8441/v1/node/list`；检查业务码、online、address、updateAt |
| 单节点真实健康 | 将列表的 `id` 从 Base64 解码为 ASCII hex，再请求 `/v1/node/health?id=<id>`；必须业务码 0 且为 Green/Yellow |
| 评分历史心跳 | `/v1/node/gethbnum?id=<id>`；返回 `heartBeatTotal`、`heartBeatMax` |
| 今日分钟心跳 | `/v1/node/gethbnum?id=<id>&ctime=<当前Unix纳秒>`；仅诊断心跳在增长，不能替代健康历史窗 |
| 模型命名空间 | `GET http://127.0.0.1:8441/v1/file/getns?name=paddlempc`，第二方改为端口 `8442`；读取 `data.namespace.replica` |
| 汇总参考 | `/v1/file/getsyshealth`；只作参考，不能仅凭 sysHealth 或文件颜色推导新模型可写性 |
| 保留失败任务 | `GET http://192.168.45.101:18101/api/v1alpha1/paddledtx/task/get?taskId=7c9f47bd-65f3-4a61-874d-c5dc8ba7c5ac` |

实际 eligible 条件应按每个模型 dataowner 的 namespace 副本要求计算：`Online && health in {Green,Yellow}` 的不同 storage 节点数至少为 `replica`；业务码或查询失败时不能报告 ready。

## executor 第二个解析调用点

共享元信息补丁还覆盖 `executor/handler/mpc.go` 的 `getTargetPart`。当前源码中它没有活动调用，唯一旧调用已经注释；两个运行中 executor 二进制的函数元数据中均无 `getTargetPart`，而实际使用的 `getTaskParticipantParam`、`SaveModel` 均存在。当前执行路径使用 requester 已校验生成的参与方标记，不调用这段元信息解析。

因此本轮不是漏部署一个实际可达的新解析路径；没有为不可达方法重启 executor。源码补丁及该包编译已覆盖未来构建，原运行二进制均已备份，SHA256 为 `69fbca80188cf31c637904823d00c6a8e3a7ba621eccf05738e2b01390ad5723`。

## 00:10 继续验收步骤

用户已选择 **2026-11-03 00:10 中国时间**继续；托管续跑由主任务安排。

1. 复查时钟、实际节点健康、心跳历史窗和两个模型 namespace 的副本要求。若 eligible 不足，保留未就绪结论，不发布注定失败的计算任务。
2. 确认失败任务 `7c9...` 仍保留，然后只发布一个独立命名的 v2 公开任务，立即保存新 taskID，并用列表/详情确认唯一性。
3. 若出现新待批申请，仅核对其文件、applier、owner、时间与新任务关联后批准有限期限；不改历史申请。全过程继续同一个新 taskID，不因等待审批而重复发布。
4. 继续执行后，必须验证原生任务 Finished、双方模型结果 ID/文件和后续读取，不能用 Ready、ToProcess、HTTP 200 或训练回调代替模型落盘验收。

授权复用边界：本轮 file2 的授权 `976d144c-656f-4955-bd8b-b089c271eb2c` 已批准至 `2026-11-03 17:56:20`；监控器按 file/applier/owner 查询，不按 taskID 隔离。00:10 使用原两 fileIDs 的 v2 可能复用有效授权而直接 Ready，这不算又产生了一轮新申请审批。若另行要求 v2 新 Pending→审批→Finished 全链路，需要在存储真正就绪后用既有 owner/executor 发布新的公开副本，不能篡改历史有效期或制造新身份。

## 服务器证据

- `/var/log/ppci/regression-20261102/paddle-approval.json`：旧任务审批前后、关联 authID、有限到期时间，证明未由审批脚本启动任务。
- `/var/log/ppci/regression-20261102/paddle-storage-health.json`：真实节点颜色、历史及今日心跳。
- `/var/log/ppci/regression-20261102/paddle-storage-diagnosis.json`：时钟、心跳错误数、实际 namespace 副本及运行 executor 调用点证据。
- `/var/backups/ppci/office-recovery-20261102/requester-tools/executor1-before-metadata-check`、`executor2-before-metadata-check`：保留的原 executor 二进制。

本记录不宣称存储已恢复可写或 v2 训练已经成功。跨日后的真实存储/模型结果仍待续跑验收。
