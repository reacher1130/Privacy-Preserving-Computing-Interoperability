# Alice 原生合作节点机构元数据恢复

2026-11-02 19:38–19:39（中国时间，约）已恢复 Alice 现有库缺失的 Kimi 机构元数据。随后公司主机失联，当前主机健康未确认。此记录区分已观测的修复成功与尚未完成的复核。

## 原因与边界

Alice 原生 `18103` 的合作节点页调用 `POST /api/v1alpha1/nodeRoute/page`。此前实际返回业务码 `202011200`、“机构不存在”，前端把缺失的 `data.list` 显示为空；它不是成功查询后的正常空表。

Alice 的 `node.kimi.inst_id=gqxzwemm`，但 `inst` 表缺少对应行。本方机构 `rqzvglmu` 和 DemoAuth 用户上下文正常；`node_route` 两条原记录保留，按 `dst=alice` 能匹配 `r_kimi_alice`。加载该路由的 Kimi 节点详情时，`NodeManager.getNodeDTOP2P` 因缺少机构记录抛错。

原生 Alice 和统一前端均代理 Alice 的真实 Java 服务 `18080`。其业务库仍是 `db_secretflow`；当前活动协议 `paddledtx` 没有切换这份数据库。Kimi 原生列表能显示 Alice，因为 Kimi 库含双方机构记录。

## 已执行的最小恢复

[脚本](../../scripts/restore_alice_peer_institution.py) 从真实 Kimi 库及其只读 `/inst/get` API 交叉核对权威记录，仅保留以下五列：

| 列 | 权威值 |
| --- | --- |
| `inst_id` | `gqxzwemm` |
| `name` | `kimi` |
| `is_deleted` | `0` |
| `gmt_create` | `2026-07-18 03:11:03` |
| `gmt_modified` | `2026-07-18 03:11:03` |

脚本先创建权限 `0600` 的独立 SQLite 在线备份，核对真实 schema、唯一索引和双方节点引用，再在 `BEGIN IMMEDIATE` 中重验快照与冲突条件，执行普通 `INSERT`。Alice 本地自增行号为 `2`，没有导入 Kimi 自增主键、用户或凭据。未使用 UPDATE/REPLACE，未更改 node/routes、地址或协议。

事务内及提交后比较了 48 张业务表的记录多重集合：只新增这一条机构记录；其他机构、节点、路由和其他业务记录均保持原样。恢复后的真实 `18103` API 返回 `total=1`、`r_kimi_alice`、`Succeeded`；用户上下文及活动协议未变。root 随后实际刷新 Ego Lite 页面，确认出现 kimi、可用、总 1 条，截图为 `p6-partner-restored.png`。

## 验证与重复执行

本机及服务器 Python 3.11 自检六项通过：WAL 库单行插入、重复 noop、并发变化拒绝/回滚、元数据冲突、软删除冲突、同名异 ID 冲突。真实恢复后默认只读预检返回 `plannedAction=noop`。

服务器可重复核对命令：

    /usr/bin/python3.11 /opt/ppci/NewProject/scripts/restore_alice_peer_institution.py --self-test
    /usr/bin/python3.11 /opt/ppci/NewProject/scripts/restore_alice_peer_institution.py

默认只读。只有明确传入 `--apply` 才进入备份和恢复流程；已有完全相符的权威记录时只验证并 noop，冲突或软删除均拒绝。本轮已执行一次恢复，不应因页面等待或断网重复补行。

## 备份与证据

备份位于服务器：

    /var/backups/ppci/office-recovery-20261102/alice-peer-institution/20261102T113807067029Z.sqlite

SHA256：`cdbfed350ce76bb21855f388451cb2ebd9d181d28bb589ae5cc7efe07c87f962`。备份是权限 `0600` 的完整业务库，须保留私有访问控制。脚本没有自动整库回退逻辑；如需恢复，应先停 Alice，保留当前 DB/WAL/SHM，核对备份之后的业务写入，再审阅离线恢复方案，禁止覆盖运行中的 WAL 数据库。

远端成功执行时已写入：

    /var/log/ppci/regression-20261102/native-alice-peer-institution-restore-20261102T113807067029Z.json

[本机公开聚合摘要](evidence/native-alice-peer-institution-restore.json) 来自已收到的成功 tool 输出及 root 独立页面报告。**远端完整 JSON 尚未复制**，不能把本机聚合文件描述成远端原件的逐字节副本。脚本 SHA256：`054aa8961a6b4722bcd957ebcebad88f078796df5eccb8898b7e7c01cb12eeff`。

## 未完成复核

最终只读地址对照发生 SSH 超时；再次只读连接返回 `Host is down`，root 也确认 SSH 2222、HTTP 18101 均不可达，已停止重试。不能宣称当前主机健康。

Kimi 页面此前展示合作方 Alice 地址 `192.168.117.4`、本方 Kimi 地址 `.2`；此前报告曾认为 Docker Alice 为 `.2`、Kimi 为 `.4`。本轮未收到最终 Docker/数据库/API 地址对照结果，暂不能断言是旧地址或 DTO 方向错误；没有改地址。

11/3 00:10 续跑须先验证主机连通，再只读取回远端完整证据、核对合作列表与真实地址、检查 XDB 存储就绪。此次列表恢复不等同于全部网页业务通过，也不证明链桨模型存储已恢复。
