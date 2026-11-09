# 本地多协议验收记录（2026-09-05，持续更新）

## 验收边界

本次使用实际 Tabbit 浏览器页面和本地容器。为补测真实页面，已按用户授权将本地 Alice/Bob/Kimi 数据库中的 admin 密码重置为用户提供的值；业务页面仍使用本地开发免认证模式，不代表生产鉴权验收通过。

## BFIA Alice → Bob：双节点 PSI 闭环通过

- 前端：Alice `http://127.0.0.1:18102`（最新修复开发构建）；Bob `http://127.0.0.1:28101`（审批测试静态构建）。
- 项目：`bfia-ui-20260905-1618`，ID `515c1f5ab0d540949832ec4d59d0978f`。
- 项目审批：`a0dea5eeb99f4fabbd85f007bb4119e3`，Bob 页面同意，Alice/Bob 均 APPROVED。
- 流程：`ui-psi-accepted-1`，画布 ID `hdzwabpk`。
- 实际鼠标拖拽两个样本表节点 `33`、`35` 与 `ecdh-psi` 节点 `37`，连接两条输入边；页面分别选取 Alice/Bob 数据集与 `id` 求交键。
- Alice 页面提交冻结流程、发起申请；Bob 页面同意；流程审批 `bc17e917c1d44e0db8d69626cda0490d` 为 APPROVED。
- Alice 页面点击执行，返回作业 `nkrl`，任务 `nkrl-50d964374ef3`。
- Alice、Bob 各自 KusciaJob 状态均 Succeeded；Alice JobStartStageSucceeded、Bob JobStartStageSucceeded。
- 真实 AppImage `ic-ecdh-psi` 使用 `secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/morse-ecdh-header:20251113`。
- Alice 输出 `/home/kuscia/var/storage/nkrl-host-0/nkrl-50d964374ef3-result`；Bob 输出 `/home/kuscia/var/storage/nkrl-guest-0/nkrl-50d964374ef3-result`。
- 两方交集均为 `1002,1003,1004,1006`，与两个各 6 行 fixture 的预期完全一致。Alice 保留 age/income，Bob 保留 score/label。
- 点击画布 `psi_output`，页面显示作业 nkrl、4 行及 Alice 三列真实数据；刷新画布后再次打开结果成功。
- 点击“下载结果 CSV”，真实文件保存到 `/Users/gaofeng/Downloads/nkrl-hdzwabpk-node-37-output-0.csv`，读取核对为相同 4 行。Tabbit download 事件未返回，但浏览器实际已完成保存；未重复点击。
- 页面截图：`/Users/gaofeng/Library/Application Support/Tabbit/LocalAgent/Runtime/artifacts/task-e951bade-c46e-4818-bde8-03dffe4bbaa8/bfia-nkrl-result-ui-shot-3bcdce92-3672-4dc4-b9a5-3521e14b9935.png`。

测试输入位于 `NewProject/testdata/bfia-ui/{alice,bob}.csv`，通过 Docker 文件复制及 BFIA 元信息 API 准备，然后在页面选择。此项不代表文件上传 UI 通过。

## 本次发现并修复的主要问题

1. BFIA 项目列表分页响应不匹配导致白屏；机构 ID 与节点 ID 混用；项目参与方不完整与审批结果虚报。
2. 画布新建 ID、节点索引持久化、H2 migration 和节点更新逻辑不匹配；真实配置保存此前失败。
3. BFIA 数据集字段查询误走原生项目服务；字段选择未随上游数据更新。
4. 提交/申请/确认缺少真正的双节点流程状态机；现在执行前要求项目及流程审批通过。
5. 结果数据行被旧版表结构组件读取，导致 `fields.split` 崩溃；增加独立 BFIA 数据行展示/CSV 导出，保留元信息展示分支。
6. 刷新画布丢失作业状态、隐藏结果入口；加载时合并最新执行状态。

验证：后端 11 项针对性测试通过，Maven `-Dmaven.test.failure.ignore=false` 构建成功；前端 Node 18 容器 Umi 编译成功，`/workspace/node_modules/.bin/tsc --noEmit` 退出 0。

## 协议切换与引擎映射

- Alice 页面真实点击并确认四个入口：`隐语原生`、`BFIA`、`FATE`、`链桨`。
- 后端 `/api/v1alpha1/config/protocol` 返回 `supportedProtocols=[secretflow,bfia,fate,paddledtx]`，并在切换时同步返回：SecretFlow/Kuscia、BFIA interconnect adapter、FATE-Flow/fate2-adapter、PaddleDTX/paddlempc。
- 页面入口与后端 active protocol 同步；切换后算子/管理页面随协议变化，不是只改显示标签。
- 原生项目列表已与 BFIA 项目隔离；BFIA 使用自己的项目接口和结果格式标记。

## 最终构建部署复验（23:20 后）

- 最新 Umi 生产构建退出 0，发布到现有多节点 nginx 容器；入口 Alice `18101`、Bob `28101`、Kimi `38101`。生产构建仍对接本地测试后端，不代表生产环境部署。
- Alice Java 后端已加载包含 FATE/链桨适配器的最新 jar；Alice、Bob、Kimi 均使用本地演示免认证配置。
- 新浏览器 origin 以 `local-dev-auth-disabled` 前端开发标记进入已关闭鉴权的本地 Alice 后端；该步骤绝不记作登录成功。
- 原生工作台页面仅显示原生 `alice-kimi-psi`，不再出现 BFIA 项目 `bfia-ui-20260905-1618`。
- 实际点击 BFIA 切换、确认、我的项目；悬停项目卡片后点击进入，进入 `ui-psi-accepted-1`；再次点击 `psi_output`，生产页面显示作业 nkrl 和相同 4 行结果。
- 最终 TypeScript 检查退出 0（`/tmp/secretpad-ui-final-typecheck.log` 空），两个代码仓库 `git diff --check` 通过。未提交/推送用户已有或本次改动。
- 最终测试实例 Alice 活跃协议为链桨；Alice–Bob–Kimi Kuscia、FATE guest/host Flow 和 PaddleDTX 双 executor 均保留运行。

## FATE adapter：双节点画布闭环通过

- FATE 页面注册并切换到 `FATE-2.2-local-e2e`，画布组件实际使用 `psi`、`coordinated_lr`（另提供 `hetero_secureboost` 模板）。
- FATE guest/host 使用两个 `federatedai/standalone_fate:2.2.0` 容器（本机 `19381`、`19382`），数据集绑定到两方，页面拖拽、连边、保存和提交均通过。
- 页面提交返回本地作业 `fj-276dce85b0274aa8`；guest/host 两个 fate2-adapter 日志均完成 READY→FINISHED，关联 Kuscia jobs 均为 `Succeeded`。
- 修复 `/v1/interconn` 探测路径、GET JSON body 和 FATE 错误信封校验；FATE 不是只做接口 200 检查。

## 链桨（PaddleDTX / paddlempc）：双执行器画布外任务闭环通过

- 页面入口 `链桨（PaddleDTX）适配器` 显示 `paddlempc`、双节点可达、executor 探测 HTTP 200；表单支持 `linear-vl`/`logistic-vl`/`dtc-vl`、双方文件、执行器、PSI、`label` 和 `labelName`。
- 前端真实点击“发布并执行”创建任务 `6a6636a6-9ad7-4fd8-9230-2f622d6b3155`；页面回显 publish 的 TaskID、自动 `task start` 的 `OK`，并轮询到 `Status: Finished`。
- 链上复核：两方数据均 `ConfirmedAt=2026-09-05 23:17:55`，`StartTime=23:17:58`，`EndTime=23:17:59`，`ErrMessage` 为空，Result map 含 executor1/executor2 两份结果 ID。
- 后端已处理 XChain Confirming→Ready 的异步窗口、CLI 应用层错误（旧 CLI 仍可能退出 0）和 Finished/Failed 终态；页面不会再把链上拒绝误报成成功。
- `shared-exchange-Connectivity/PaddleDTX/testdata` 的 executor compose 已整理为两个带配置/密钥/日志挂载的本地执行器，XChain compose 自动加入外部 `blockchain_network`；两份 compose `docker compose config` 校验通过。

## 仍未完成，不得扩大验收结论

- Kimi SecretFlow 原生完整项目/画布/执行/结果 UI 闭环。
- BFIA 其他训练/统计算子的全部执行与结果，及完整 UI 文件上传。
- FATE：本次验证的是 `psi` + `coordinated_lr` 双节点画布闭环；不等价于所有 FATE 算法/参数组合均通过。
- PaddleDTX：本次验证的是 `linear-vl` 双执行器训练；不等价于 `logistic-vl`、`dtc-vl`、predict 和生产链部署均通过。
- 生产鉴权、访问控制、安全验收；页面时间字段的时区一致性仍需单独复核。

以上结论仅覆盖本记录明确列出的协议、算子和 fixture；不代表未列出的算法组合、生产鉴权或生产部署已通过。
