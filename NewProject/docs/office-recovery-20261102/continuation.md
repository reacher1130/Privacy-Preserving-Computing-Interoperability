# 2026-11-03 00:10 跨日验收

用户已明确批准北京时间 11 月 3 日 00:10 自动继续本聊天的剩余工作。工作区为 `/Users/gaofeng/develop/project/Privacy-Preserving-Computing-Interoperability`，分支 `codex/office-recovery-20261102`。遵循 AGENTS.md，先 board/search，复用进行中的 spec 006；先看本目录 README、webpages.md、FATEBoard.md 和相邻的存储信誉、元信息兼容、管理恢复文档，以及当前 Git 状态，不覆盖其他未提交修改。

公司 Linux 为 `root@192.168.45.101:2222`，沿用现有 SSH 认证和严格主机校验。source、build、runtime 分别为 `/opt/ppci-source`、`/opt/ppci-build`、`/opt/ppci`。保留已有数据库、账本、文件、模型、身份、失败任务及 `/var/backups/ppci/` 的所有回滚材料；不重注册原节点、不改健康历史/阈值、不跳门禁、不切 Local 制造成功，不整目录覆盖或强制重置。敏感凭据和私钥留在服务器，不输出、不下载。

收口时服务器曾突然失联（SSH Host is down、HTTP 000），最后的全机状态复核与本机新报告向服务器源码目录同步尚未完成。先确认当前 SSH/HTTP 连通；离线时不要重跑任何写库或发布。Alice 缺失的既有 Kimi 机构元信息已经 insert-only 恢复，保留原 gqxzwemm 身份，48 表其他记录集合未变，原生网页实际显示合作节点可用；恢复脚本默认只读，已重复预检 noop，不应盲目再 --apply。新原生下载补丁及生产构建已发布，真实 CSV/meta 浏览器下载通过；见 native-download.md 与证据。恢复连接后先读本机 Git 的最后报告、取回未复制的恢复证据，再复核实时状态。

首先实查 Alice `/api/v1alpha1/paddledtx/status` 和 DataOwner `127.0.0.1:8441/8442`：两个 `paddlempc` namespace 副本均为 2，分别至少两个 Online 且 Green/Yellow 的节点才可写。旧评分只用过去 7 个完整日，11/2 的真实心跳在 11/3 零点才纳入；无挑战时评分为 `0.595 + 0.3 * HB / 10080`，每节点至少 168 条历史真实心跳才达 Yellow。必须以当时真实 API 结果为准。机器离线或未合格时，不发布注定失败任务，保留未完成状态并报告具体原因。

已完成源码归档、前后端修复、528 项 Java 全量及随后 19 项存储诊断定向、32 项前端、TypeScript、全量 ESLint 零错误、八算法数值/协议 8/8、隐语/BFIA 双方 PSI、原生及平台 FATE PSI/LR、管理端签名和公开文件流程。存储门禁版本已发布，两侧真实 XuperDB 探测 checked=true、eligibleNodes=0、replica=2、storageReady=false；runtimeHealthy=true 仅说明运行层正常，不代表模型可写。前端现优先显示真实存储错误，不能跳过此门禁。未受新变化影响的通过项无需重复运行；如本轮再改相应代码，则补对应验证。

失败训练 `7c9f47bd-65f3-4a61-874d-c5dc8ba7c5ac` 已真实验证发布→待审批立即返回→刷新找回同 ID→精确审批→网页继续，但模型保存因 `empty healthy nodes` 失败；保留它，不改状态、不自动重试 Failed。原 file2 授权 `976d144c-656f-4955-bd8b-b089c271eb2c` 有效至 11/3 17:56:20，按 file/applier 复用，不可冒充新审批。

存储 ready 后，以既有 owner/executor 身份和仓库公开 Boston CSV 新建独立时间戳 namespace/公开副本，不修改旧文件。路径可参考 `NewProject/scripts/environments/paddle-demo-data.py`，先确认实际容器路径。创建唯一命名的 v2 训练，保留 publish 的 taskId；验证 Confirming 时刷新找回且同名仅一条。只审批精确关联本 taskId 的公开文件申请并设有限期限，随后从网页继续同一 ID，等待 Finished 并核对双方模型产物。再用该模型做公开预测，核对 Finished 及输出；终态再 start 应幂等，不重跑或重复 publish。

浏览器使用 Ego Lite/ego-browser。11/2 的公司网页验收使用 TaskSpace 7（仍保留，未因断连创建替代空间）；断连前可直连真实公司 IP，Alice/Bob/Kimi 为 18101/28101/38101，隐语原生 Alice/Kimi 为 18103/38103，FATEBoard 为 19383，链桨原生管理为 18511。用户要求逐个打开并操作真实内网页面，不能只看总平台或本地构建。先检查空间归属；若仍归代理则复用；如已被用户接管，遵循技能的交接规则，不擅自接管，也不另建空间绕过阻塞。临时转发仅在直连确有失败时使用，结束关闭。custom requester 双格式兼容已在两个 executor 的 `/home/requester-cli-demo` 部署，普通重启保留；不要用 stock CLI 或旧镜像覆盖。新管理端 `ppci-dtx-manager` 及独立 `data` 合约已恢复，原生网页登录和公开资源详情已经验证；新管理库的模型/任务列表为空，不代表既有计算任务丢失。不要重跑安装覆盖管理库；原 `paddlempc` 保留。

新证据放入 `/var/log/ppci/regression-20261102/` 的独立日期子目录，记录 task、授权、双方模型和预测 ID；仅公开摘要同步本机。完成后复核 29 个受管容器、3 后端、管理接口、真实 storage ready、原数据身份集合和备份；必要发布先备份并沿用回退机制。提交准确的代码/报告，不推送未明确请求的远端。只有完整必要闭环通过后才将 006 标 complete；否则保留进行中并说明剩余项。
