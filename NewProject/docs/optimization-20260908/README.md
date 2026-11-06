# 全套常驻服务资源优化（2026-09-08）

保留 Alice 四协议、Bob BFIA、Kimi 原生隐语，以及独立原生 FATE Guest/Host 和 PaddleDTX。28 个现有容器和三个宿主机后端保留，没有改成按需启动，也未删除业务数据、账本、模型、历史结果或功能镜像。

## 已部署

- 后端日志不再为 INFO 输出序列化完整 HTTP 请求/响应；保留 DEBUG 定位能力。
- BFIA 每五秒仅查询未完成任务的 ID，不再加载全部历史任务的 DAG 和配置。同步行为和协议门禁保留。
- 三个后端保留 Xmx768m、Xms128m，开启 G1 周期回收、字符串去重，空闲堆比例设为 20/40；当前 JVM 通过管理接口同步应用空闲堆配置。
- 关闭 Alice 原始 SQL 标准输出；引导日志与滚动业务日志分开，避免多个写入器操作同一个日志文件。
- Alice 数据库池允许两个连接（最低仍一个），处理启动数据库初始化与任务监听争用单连接导致的启动超时。
- Fateboard 初始堆 2GiB 降至 128MiB，最大堆为 768MiB；入口等待 Flow、Fateboard 实际 HTTP 就绪，消除慢启动时反复重启。原生参考 Flow 保留。浏览器已验证登录、RUNNING 页面与 JOBS 列表导航（原生参考 Flow 中暂无任务，与 Guest/Host 任务状态分开验证）。
- BFIA 算子注册改为一次批量提交和一次批量检查，保留所有算子。
- 安全压缩两个不再打开的 Kuscia Envoy 历史日志；逐文件 SHA256 和解压校验后替换，净节省 **1,097,708,760 字节（约 1.02 GiB）**。详情见 log-compression.json。
- 清理已确认终止的本次 FATE 验收任务残留的八个 Python 工作进程；只终止进程，保留所有任务文件。详情见 fate-terminal-workers.jsonl。

## 验证

Maven 指定的 21 项测试通过（backend-build.log）。批量 BFIA 注册脚本已实跑成功，两侧路由恢复 Ready，后端保持运行（bfia-batch-registration.log）；Shell/Python 语法检查与 Git diff --check 均通过。运行态检查确认 28 个容器、三个后端、四条协议路由均正常（runtime-final.json）。

- 原生隐语：新任务 lice 三个节点均 SUCCEED，native-result.json。
- BFIA：新任务 cnwr 三个节点均 SUCCEED，bfia-result.json。
- PaddleDTX：新预测任务 0e24f936-bc02-43a4-9520-5ed0db342b43 Finished，两个执行方确认，paddle-retry-submit.json。
- FATE：首轮超时并残留工作进程，已清理。新原生任务 202609080236267976040 的 Guest、Host、Arbiter 均成功，数据读取、PSI、两轮联合逻辑回归均已完成；平台任务 fj-63de3ab5fbf54dc2 也已回传 SUCCESS，详见 fate-final-*.json。

## 资源口径

resources-before.json 为服务冷启动阶段，只有 27 个容器可采样（Fateboard 当时重启）；resources-after.json 为运行任务后的 28 容器。两者不可直接作为等负载的总内存节省对比。三个旧 JVM 周期回收前后的物理占用约降低 25.7 MiB；后续同一组新 JVM 经空闲堆比例调整和一次回收，从 2612.8 MiB 降至 2067.5 MiB，减少 **545.3 MiB（约 20.9%）**；见 resources-after.json 与 resources-after-reclaim.json。该差值是现场回收效果，并非高负载峰值承诺。配置上限降低不等于已测得同等实际节省。

本轮未清理功能镜像或容器，也未清理业务数据库。回滚文件保存在 ../../.local-backups/optimization-20260908/。

## 维护入口

- `python3 NewProject/scripts/platform_runtime.py start`：恢复现有完整常驻拓扑，保留原容器数据。
- `python3 NewProject/scripts/platform_runtime.py status`：检查容器、后端、路由、原生 FATE 与链高度一致性（不替代真实任务验证）。
- `python3 NewProject/scripts/compress_archived_kuscia_logs.py`：仅压缩已关闭的历史 Envoy 日志；内容校验后替换。
- `python3 NewProject/scripts/cleanup_terminal_fate_workers.py <native_job_id...>`：默认只检查；`--apply` 才终止匹配的残留工作进程。要求两侧 API 均确认指定任务处于终态。
- `python3 NewProject/scripts/configure_fateboard_runtime.py`：在现有 Fateboard 容器上应用内存参数和启动恢复修复。

本轮 Java 改动已构建为本地运行 JAR；没有提交 Git 或推送远端。工作区还包含前期拓扑改造的未提交修改，本轮未重置它们。

最终采样时间 2026-09-08T10:57:57.126175：28 容器约 8.07 GiB，三个 JVM 物理占用约 2.00 GiB，合计约 10.07 GiB；不包含 OrbStack 虚拟机自身及其他宿主机应用开销。见 resources-final.json。
