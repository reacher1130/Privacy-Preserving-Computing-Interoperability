# 开放互联平台本地验收与清理（2026-09-07）

> **FATE 结论更正**：本记录的旧 FATE `SUCCESS` 仅证明适配器退出，不能证明原生算子成功。后续发现旧 BFIA 状态接口会将失败任务汇总为 `FINISHED`。该结论已撤回，旧记录在平台标为 `UNVERIFIED`；真实原生验收及正确拓扑以 [固定拓扑改造记录](../topology-20260907/README.md) 为准。其他协议证据不受影响。

## 范围与入口

本轮是在既有本地三方环境上完成四协议关键路径回归、运行故障修复和保守清理。验收不等同于生产发布，也不覆盖每个算法的全部参数组合。

- Alice 总平台：http://127.0.0.1:18101/edge
- Bob 总平台：http://127.0.0.1:28101/edge
- Kimi 总平台：http://127.0.0.1:38101/edge
- 总平台菜单保持既有原生布局；切换协议后，通过新增的“进入协议工作区”按钮进入对应管理页面。
- BFIA、FATE、链桨工作区分别为 `/protocol/bfia`、`/protocol/fate`、`/protocol/paddledtx`。

本地免登录演示设置沿用此前配置。链桨演示仍使用 `PADDLEDTX_DEMO_SKIP_HEALTH=true` 跳过历史七天健康统计门禁，实际在线/链上查询和执行未跳过。链桨由 requester CLI、XChain、双 executor 执行，不能当作 Kuscia AppImage 调度证据。

## 本轮已修复

1. 原生结果节点 ID 兼容：`new-n3` 等不符合旧三段格式的 ID 不再引发结果页白屏。
2. BFIA 项目/流程链接回到正确协议工作区；旧 `/edge` 协议链接兼容跳转；导入图缺少名称/坐标时补充可读名称与布局。
3. FATE 画布显式绑定提交服务上下文；列表过滤过时响应，防止跨集群或旧请求覆盖当前数据；实际调度日志确认创建请求超过旧 5 秒期限被取消，因此将创建操作期限改为 60 秒。失败记录返回非零 API 状态，查询不到调度记录时保留错误信息。
4. 链桨健康检查同时验证两台 executor 的 HTTP 状态与业务返回码；一台失败即未就绪，并拒绝协议切换。
5. 链桨 CLI 使用有界等待，超时终止进程树，避免先读取输出导致超时失效；预测表单传递并要求训练任务 ID；失败结果不再提示执行成功。
6. XChain 恢复停机节点、降低过大的缓存配置，并添加重启策略。保留原容器内账本，未重新创建有状态容器。此修复验证即时恢复，不构成长时间稳定性承诺。
7. Maven 子模块不再忽略测试失败；本轮构建失败会直接阻断发布。

## 验证证据

- 后端选定回归测试：21 项通过、0 失败、0 跳过，包含 FATE Flow 真实只读探测。见 `backend-tests.log`；并非完整仓库测试全集。
- 前端：TypeScript 检查及 Umi 页面构建均通过，见 `frontend-build.log`；新增 4 项 Jest 竞态回归全部通过，验证跨集群返回顺序及同集群旧状态覆盖问题。
- BFIA 聚合算子测试：Python SGB、HE-WOE；C++ ECDH-PSI、SS-LR、SS-XGB、SS-Pearson、SS-VIF、SS-Compare，共 8 项通过。见 `algorithms.log` 与 `algorithms/`。这组脚本证据与下方页面操作证据分别记录。
- 隐语原生：页面点击“全部执行”得到新作业 `buhf`，项目 `gzbnqqso`、画布 `thrxhlxi`、三节点成功。结果面板可打开，点击下载显示完成。见 `native-status.json`。
- BFIA：页面执行已批准流程 `iqdcehaj` 得到新作业 `bepi`，Alice/Bob 真实执行，三节点成功；页面展示 `id/age/income` 四行交集（1002、1003、1004、1006），并点击下载 CSV。见 `bfia-status.json`。
- FATE：通过真实页面绘制 PSI→coordinated_lr、绑定 breast_hetero_guest/host 并提交最终作业 `fj-df9d0daa7f5d4e92`。双方审批通过、Kuscia Succeeded、页面 SUCCESS，约 60 秒完成。见 `fate-status.json`、`fate-kuscia.json`。前两次超时失败记录保留作为诊断历史。
- 链桨页面训练：`7109ac57-fdaf-4a2e-a98a-5c09a97542b1`，双执行器确认并完成 linear-vl 训练；页面预测：`88cb092a-8a9f-40c4-ba1c-a75fc68cb099`，引用本次训练模型，状态均为 `Finished`。通过 requester 另行取回 456 行预测值，见 `paddledtx-train.json`、`paddledtx-predict.json` 和 `paddledtx-predictions.csv`。预测复用演示训练数据，仅验证执行链路，不作为独立测试集精度评估。
- 链桨故障注入：停止 executor2 时，状态 `ready=false` 且协议切换被拒绝；随后恢复 executor2。见 `paddledtx-one-node-down.json`、`paddledtx-switch-rejected.json`。

## 运维与清理

在项目根目录执行：

```sh
python3 NewProject/scripts/platform_runtime.py status
python3 NewProject/scripts/platform_runtime.py start
python3 NewProject/scripts/cleanup_platform.py
python3 NewProject/scripts/cleanup_platform.py --apply
```

`start` 只恢复已安装的容器与后端，缺失容器会报错；它不是从空机器安装脚本。XChain/FATE 等状态包含容器可写层，禁止用强制重建代替恢复。

清理工具默认只生成清单，应用时只删除明确列举的已停止容器、未被任何容器引用的旧试验镜像，以及可再生/重复文件。保留当前静态站点、原生对照站点、账本、数据库、数据卷、源码仓库、依赖和编译缓存。镜像逻辑大小包含共享层，不能当作磁盘实际释放量。

## 本机资源处理

本轮测得主机物理内存 24 GB、交换空间使用约 19 GB。三个本地 Java 启动脚本增加 768 MB 堆上限和 2 个处理器的线程配置。停止本项目当前未使用的 CodeGraph 索引服务（约 2.4 GB），索引文件保留，见 `stopped-index-service.json`。前端构建容器限制 2–4 个 CPU，构建完成后已自动删除。XChain 实际进程设置 `GOGC=50`、`GOMAXPROCS=2`，三方后端启动等待上限调整为 300 秒。未停止其他项目的服务。

## 最终清理与健康结果

已执行清理：2 个已停止废弃容器、3 个未被容器引用的旧 PaddleDTX 试验镜像、60 个文件/目录清单项（115,848,293 字节，约 110.5 MiB）。镜像逻辑大小合计 865,995,187 字节，包含共享层，不代表实际释放空间。完整清单见 `cleanup-applied.json`。此前已停止并自动删除闲置的前端开发容器。

清理后 28 个项目运行容器正常，Alice/Bob/Kimi 后端可访问，两个链桨 executor 链上查询成功，三节点账本高度一致，汇总 `healthy=true`，见 `runtime-status.json`。保留现用镜像、数据卷、账本和数据库；原生对照站点仅保留参考用途，本轮不宣称其独立后端全部验收完成。

另外删除本轮已结束的临时前端构建副本、临时 Go 编译缓存及未部署的 ARM 合约诊断候选，共 3,550,590,179 字节（约 3.31 GiB），见 `cleanup-temporary.json`。XChain 继续使用原合约，未进行链上合约升级。
