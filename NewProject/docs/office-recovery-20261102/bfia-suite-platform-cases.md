# 办公平台四条业务用例

2026-11-03 办公机 `192.168.45.101`。下表把此前实际浏览器操作和计算验收，与本次对既有任务的只读复核分开。这四条平台用例只查询了表中已有任务 ID，没有重新提交或重跑；八算法套件的独立运行另行记录。

| 用例 | 此前实际验收 | 本次只读复核 |
|---|---|---|
| BFIA Alice → Bob | [Alice](http://192.168.45.101:18101/edge?ownerId=alice) 与 [Bob](http://192.168.45.101:28101/edge?ownerId=bob) 实际完成同一合作申请以及项目 `c07d476919db43b992a5f6f79f0b3bee`、流程 `ucplzxzq` 审批。Alice 在网页执行 ECDH-PSI `srbm`；双方在原画布预览并下载本方 CSV，交集均为 `1002、1003、1004、1006`，只含各自本地列。[验收记录](../../../specs/007-bfia-platform-workflow/README.md#notes) | `srbm` 在 Alice、Bob 的 Kuscia `cross-domain` 对象均为 `Succeeded`。Bob 的结果入口为已审批画布，未验收其全局结果历史。 |
| 隐语 Alice → Kimi | Alice 创建原生项目 `wckkekky`，Kimi 网页通过原邀请。共享存储与结果投影修复后，Alice 从画布 `yoyytwos` 提交新作业 `klao`，三节点成功。双方成果页自动出现 `klao-new-n3-output-0`，真实网页下载均为四行同样的交集 ID，各自仅含本方列。[验收记录及页面入口](../../../specs/007-bfia-platform-workflow/README.md#录屏顺序) | `klao` 在 Alice、Kimi 均为 `Succeeded`。早先缺文件的 `zbza` 仍为 `Failed`；`mtwx` 是中间验证，Alice 曾单独补录其结果索引，最终 `klao` 无手工补录。 |
| FATE 原生双端 | Alice 平台实际提交 PSI `fj-ad8ad22aead149a1` 和画布 PSI＋联合逻辑回归 `fj-971563559ab84ded`。原生双方 PSI 各 569 行；LR Guest、Host、Arbiter 均成功，双方模型元数据 `epochs=end_epoch=2`。实际打开 [FATEBoard](http://192.168.45.101:19383/#/history) 的成功作业图并检查 LR 参数。[平台到原生映射](evidence/platform-fate-summary.json) · [Board 证据](FATEBoard.md) | 原生 Flow 19381/19382 `/v2/job/query` 查询 PSI `202611020938484364900`：Guest、Host 成功；LR `202611020945328298380`：Guest、Host、Arbiter 成功。两轮未收敛；无重载模型后预测的验收证据。 |
| PaddleDTX 原生双执行器 | Alice 实际网页发布纵向线性回归训练和新预测；待审批时刷新找回同一 ID，批准对应文件授权后继续原任务。双方模型分别为 631/912 字节，在真实 `paddlempc` XDB 保存并按执行器身份读回；签名 RPC 返回独立公开输入的 50 行预测，ID 匹配且预测值有限。[跨日验收](paddledtx-crossday-acceptance.md) · [模型读回摘要](evidence/20261103-acceptance/paddle-model-readback.json) · [预测结果摘要](evidence/20261103-acceptance/paddle-prediction-result.json) | `/api/v1alpha1/paddledtx/task/get`：训练 `7c442cd7-2d64-4dd7-98ec-5a0a2df700d7`、预测 `6a7fd227-7525-4c63-ba11-f56c530951a2` 均 `Finished`；旧失败 `7c9f47bd-65f3-4a61-874d-c5dc8ba7c5ac` 保留。`ready=true`，两侧 XDB 都已检查且合格节点 2、要求副本 2。未验收其他算法或模型泛化质量。 |

FATE 和 PaddleDTX 各自使用独立的原生双端引擎。Alice 是统一业务入口；上述证据未覆盖两种厂商引擎在同一个 MPC 会话中直接互算。BFIA 的 Alice/Bob 使用同一 BFIA 实现；隐语的 Alice/Kimi 使用隐语原生路径。

## 本次运行状态及算法口径

严格校验主机键的 SSH `192.168.45.101:2222` 可达；`ppci-platform status` 返回 `healthy=true`、`runtimeHealthy=true`、29 个容器、0 错误。统一平台 18101/28101/38101、原生隐语 18103/38103、FATEBoard 19383、链桨管理 18511 的对应入口均 HTTP 200。首页和运行健康不替代上表的作业及结果证据。

- [此前八算法独立验收](../bfia-eight-algorithms-numerical-protocol-20260914.md)覆盖 ECDH-PSI、SS-LR、SS-XGB、SS-Pearson、SS-VIF、SS-Compare、SGB、HE-WOE 的真实双方数值及通信证据。
- Alice、Bob 的 Kuscia 各有 `ic-ecdh`、`ic-ecdh-psi`、`ic-ss-lr`、`ic-ss-xgb`、`ic-ss-pearson`、`ic-ss-vif`、`ic-ss-compare` 七个 AppImage 名称；两个 ECDH 名称同属 PSI，实际为六项算法。七个对应 CRI 标签均已装载，指向同一摘要 `sha256:266ed2fd62a9f1cb1dd3aa96e6a3bc6a4ee4db950bd26edc0d56d23cd9090f79`。
- 两端实时 `/v1/interconn/components/list` 均返回 `datatable`、`secureboot`、`ecdh-psi`、`ss-lr`。其中三个计算算法是 ECDH-PSI、SS-LR 和由旧组件键 `secureboot` 调用的 SS-XGB（[转换器](../../secretpad/secretpad-service/src/main/java/org/secretflow/secretpad/service/graph/converter/BfiaJobConverter.java)）。这条 SS-XGB 路径与独立 Python SGB 不同。上表最新双边网页闭环仅覆盖 BFIA 的 PSI。SGB、HE-WOE 使用独立 Python 回归运行环境，办公 Docker 中有 `ppci/bfia-python:amd64-20260908`，两项均未注册为 Kuscia AppImage。

## BFIA 平台套件验收

在 [Alice 内网算法中心](http://192.168.45.101:18101/edge?ownerId=alice&tab=bfia-components) 点「一键运行八算法」。页面立即显示 SGB 运行中、后续项排队，刷新后找回同一运行 `76c645a7-81cc-4a64-9470-e614762b5e1f`，约 104 秒后显示 **8/8 通过**。从网页实际导出 [JSON 验证报告](evidence/20261103-acceptance/bfia-suite-report.json)，SHA-256 为 `3bfecc6e2e2fc04f712112e35f10df81ed936d9b986c2076933d666da442ec52`。

| 算法 | 数值 | BFIA 协议 | 结构化事件数 |
| --- | --- | --- | ---: |
| SGB | 通过 | 通过 | 696 |
| HE-WOE | 通过 | 通过 | 34 |
| ECDH-PSI | 通过 | 通过 | 24 |
| SS-LR | 通过 | 通过 | 30 |
| SS-XGB | 通过 | 通过 | 30 |
| SS-Pearson | 通过 | 通过 | 28 |
| SS-VIF | 通过 | 通过 | 28 |
| SS-Compare | 通过 | 通过 | 26 |

Ego Lite 实际打开 SGB 和 ECDH-PSI 的 Alice、Bob 四份日志。另核验八项的 16 份日志均能从 API 读取结构化事件，服务器原始文件的 SHA-256 均与协议报告一致。Python 两个角色在同一隔离容器内的独立进程通信，C++ 在一对临时容器间通信；均只用公开样例，不创建或修改业务画布任务。外部来源、缺少请求标识、Bob 直接发起均返回 403；本次只生成一个运行目录。运行清单与原始日志在 `/var/log/ppci/bfia-suite/runs/76c645a7-81cc-4a64-9470-e614762b5e1f/`，退出码 0，临时容器与网络已退出。

此次发布只重启 Alice/Bob。四处数据库冷备共 22 个文件，旧 JAR、完整前端和回滚脚本位于 `/var/backups/ppci/releases/20261103-151618-bfia-suite.VahSK1dX/`；未重启 Kimi，29 个受管容器均健康。办公实例通过 `ppci-alice` 的专用 drop-in 启用固定执行器、私有输出目录和本机可信来源，默认部署不启用免登录执行。前端校验使用实际 `p__edge.async.js` 的 SHA-256 `4e4124e3d1e744b45888abe8d7afe41ea0fda6375258762911144c0949b0af2a`，首页哈希在新旧版本相同。

约 104 秒是公开套件的一次端到端耗时，未进行原生与互联的配对对照，因此不能用作「性能下降不超过 20%」的验收结论。

本轮旧套件及其原始日志随后完整移出活动测试目录，归档在 `/var/backups/ppci/cleanups/office-20261103-160759-fresh-platform-36e1a9cv/old-bfia-runs/76c645a7-81cc-4a64-9470-e614762b5e1f/`。原路径、文件哈希和可回滚映射见同级归档 `manifest.json`。新的四平台重跑另见 [回归记录](../../../specs/009-office-platform-fresh-regression/README.md)。

## 算法原理与协议标注

- **已有开放协议（3 项）**：ECDH-PSI 参考 PPCA 9—2023（第 1 部分），SS-LR 参考 PPCA 7—2023（第 2 部分），SGB 参考 PPCA 10—2023（第 4 部分）。[隐私计算联盟公开协议](https://github.com/caict-ppca/privacy-computing)和[隐语互联接口仓库](https://github.com/secretflow/interconnection)可复核。SGB 当前使用 Paillier；画布旧组件键 `secureboot` 当前调度的是秘密分享 SS-XGB。
- **项目自研扩展（5 项）**：HE-WOE、SS-XGB、SS-Pearson、SS-VIF、SS-Compare。扩展的是现有数学方法与密码算子在本项目中的算法接口和实现，复用 BFIA 握手及传输；不表示发明了这些算法，也不代指其他组织是否有同名规范。
- [金科联盟互联互通框架](https://github.com/secretflow/InterOp)与上述 PPCA 具体算法协议分开标注。页面「已有开放协议」表示有参考依据，本轮不作标准认证声明。

八算法接口的最终隔离 Maven 构建：538 项，537 项通过、1 项跳过、0 项失败；新增接口与执行状态测试 3 项通过。

新版算法中心在原页面显示八项原理、三步计算流程、输出、数值/协议状态及可切换的双方日志，保留报告预览和 JSON 导出。真实内网 Ego Lite 逐项核对 8 项说明和标签，在页面内切换 HE-WOE、SS-Pearson 的 Alice/Bob 日志。再次下载同一运行的 JSON，文件与原验收报告逐字节相同。无需重跑任务。

新版前端通过 38 项 Jest、TypeScript 和目标格式/样式检查。热发布的实际 `p__edge.async.js` SHA-256 为 `0620d2cc4548ef81125c563c5aaddcbd25cfd640b07505bc6b34ae80b723f2c0`。旧前端和回滚脚本在 `/var/backups/ppci/releases/20261103-153329-bfia-algorithm-ui.8hsK0xyE/`。Alice、Bob、Kimi PID 和后端 JAR 均未变化，29 个容器健康，五个前端源码文件已按哈希同步回办公源码归档。
