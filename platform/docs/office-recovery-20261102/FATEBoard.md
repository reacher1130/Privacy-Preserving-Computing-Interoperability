# FATEBoard 接线与字符串参与方修复（2026-11-02）

FATEBoard 原生页面位于 `http://192.168.45.101:19383/`。本次只修改 Board 的 Flow 地址和六个 Board Java 类；未修改原生 Flow、OSX、证书、站点身份或已有任务，也未创建额外任务。主任务已在真实公司 URL 的 Ego Lite 页面最终核验摘要、成功三节点图，点击 LR 并展开参数看到 `epochs: 2`；截图为本机回滚证据目录的 `screenshots/p8-epochs.png`。

## 两个已复现根因

1. Board 的 `conf/application.properties` 原为 `fateflow.url=http://localhost:9380`，实际访问 Board 容器自带的旧 Flow。本轮任务 `202611020945328298380` 在该地址查询为业务错误 `1001`，站点查询为 `3000`；同一容器访问正式 Guest `http://fate2-flow-guest-e2e:9380` 则均为业务成功 `0`。已改用稳定 Docker DNS。Guest 分页接口返回 `data.count=1`、`data.data` 中包含该成功任务，格式兼容 Board。
2. 详情页通过 `/websocket/progress/{jobId}/{role}/{partyId}` 一次取得 Job Summary 和 DAG。已安装 Board 2.1.0 把 `partyId` 声明为 `Integer`，但本项目的合法参与方 ID 为 `JG0100001100000010`、`JG0100001100000000`。Board 日志实际记录 `DecodeException` 和 `NumberFormatException`，导致详情全部空白。补丁将 Board 内这条调用链及同类 Summary、批量指标、日志查询保留为 `String`，并修正 HTTP DAG 控制器误把 `job_id` 传作 `party_id` 的一行。

## 实际验证

目标任务：平台画布 LR `fj-971563559ab84ded` 对应原生任务 `202611020945328298380`，角色 `guest`、参与方 `JG0100001100000010`。

修复后，在 Board 容器内使用其现有私有配置完成真实登录，检查结果如下。凭据、RSA 私钥及会话只在容器进程内使用，未输出或下载。

| 检查 | 结果 |
| --- | --- |
| 办公入口页面 | HTTP 200 |
| Guest 原生 job / DAG 查询 | 业务成功 0，任务 success，DAG 字段存在 |
| Board HTTP Job Summary | 有 job 对象 |
| Board HTTP DAG | 3 个组件 |
| Board LR Parameters | `epochs=2` |
| Board 真实详情 WebSocket | 有 `summary_date`、`dependency_data`，3 个组件，状态 success |
| 无会话访问 Board 任务详情 | 业务码 10015，拒绝访问 |

服务端证据均保留在 `/var/log/ppci/regression-20261102/`：

- `fateboard-routing-summary.json`：错误接线与正确 Guest 的对照、接线修复及详情诊断。
- `fateboard-detail-summary.json`：真实登录后的 HTTP / WebSocket 断言、匿名拒绝和 JAR 哈希，`pass=true`。
- `platform-fate-summary.json`：平台任务→Kuscia→适配器日志→原生任务映射，以及双方 PSI 各 569 行、Guest/Host/Arbiter 成功、双方 LR 模型 `epochs=end_epoch=2`。两轮尚未收敛，不据此宣称模型质量验收。

## 可复现源码与部署

- [Board 字符串参与方补丁](../../patches/fate/board-string-party-id.patch)；[源码补丁入口](../../../scripts/apply-source-patches.py) 已纳入该独立补丁，保留原有 `board.patch` 的幂等行为。
- [Board 接线/JVM 配置脚本](../../scripts/configure_fateboard_runtime.py)：在容器内备份属性文件，只设置正式 Guest 地址；不会把完整配置导出到主机。
- [Board 类兼容部署脚本](../../scripts/patch_fateboard_party_ids.py)：在临时源码副本应用补丁，复用容器内 JDK 8、当前 thin JAR 和 `lib/*`，编译六个源类；备份原 JAR 后只替换 Board 类并重启 Board JVM。编译失败时不替换运行 JAR，启动失败时恢复原 JAR。
- [HTTP / WebSocket 真实检查程序](../../scripts/CheckFateboardDetails.java)：只对既有 LR 任务执行只读查询，输出聚合断言，不输出凭据。

在办公服务器的源码工作区执行：

    python3.11 NewProject/scripts/configure_fateboard_runtime.py
    python3.11 NewProject/scripts/patch_fateboard_party_ids.py

检查程序在容器内编译运行，工作目录必须为 `/data/projects/fate/fateboard`，类路径为 `.string-party-id-build:fateboard.jar:lib/*`。本轮调用参数为 `202611020945328298380 guest JG0100001100000010`。需复验时只使用已经存在的任务，不重新发布任务。

## 备份与回滚

以下文件均位于 `fateboard-native-e2e` 容器内，未复制到客户端：

- 属性文件：`/data/projects/fate/fateboard/conf/application.properties.before-native-guest-20261102`，0600。
- JAR：`/data/projects/fate/fateboard/fateboard-2.1.0.jar.before-string-party-id-20261102`，0600。
- 修复前 JAR SHA256：`59d767ef11c069f9bbf5c909c2276aac9cfa5f4f5efbbc9ec615b63fd71fef51`。
- 当前 JAR SHA256：`fa5a5a0aa9047cd9cd89d5396a2e0808d157fd5effe6fc929b14367a2a9bd1ea`。

需要回滚类兼容补丁时，在容器内设置既有 JDK 环境，进入 `/data/projects/fate/fateboard`，先 `bash service.sh stop`，再用上述备份覆盖 `fateboard-2.1.0.jar`，最后 `bash service.sh start`。保留当前正式 Guest 接线即可恢复原有列表能力；恢复旧属性文件会重新指向错误的本地 Flow，不应作为普通类回滚的一部分。整个操作只涉及 Board JVM。

## 独立 Host Board（2026-11-03）

办公网现有两个 FATEBoard。登录后打开任务详情，点击 `psi_0`，在输出窗口检查总行数。两个站点的任务、日志和输出查询各自走本方 Flow。

| 站点 | 已有 PSI 任务详情 | 机构 ID |
| --- | --- | --- |
| Guest | [19383 · Guest 详情](http://192.168.45.101:19383/#/detail/202611030824163392980/guest/JG0100001100000010) | `JG0100001100000010` |
| Host | [19384 · Host 详情](http://192.168.45.101:19384/#/detail/202611030824163392980/host/JG0100001100000000) | `JG0100001100000000` |

Host 使用独立账号和会话 cookie。凭据由管理员从办公机的 `/var/lib/ppci/fateboard-host/credentials.properties`（仅 root 可读）交付；仓库、发布日志和验收证据不含凭据。

[部署脚本](../../scripts/deploy_fateboard_host.sh)只新增 `fateboard-host-native-e2e`，绑定 `192.168.45.101:19384`，使用现有 Board 镜像和校验过的字符串参与方补丁 JAR，后端固定为 `http://fate2-flow-host-e2e:9380`。容器由 Docker `unless-stopped` 策略恢复。原 Guest Board、两侧 Flow 的容器身份、进程 PID 与启动时间在发布前后均一致；Guest 19383 仍返回 HTTP 200。没有重跑作业或修改已有任务、输出、配置和卷。

办公网客户端直连 Host 首页返回 HTTP 200。使用 Host 账号实际登录后，HTTP 和 WebSocket 均取得指定 Host 任务，流程图两节点，状态 `success`；`psi_0` 输出接口返回总数 569。匿名任务查询被拒绝；登录后用相同任务 ID 查询 Guest 角色也无记录。随后在 Ego Lite 实际登录 19384，打开同一 Host 作业详情并点击 `psi_0 → View the Outputs`，页面也显示 569 行。

办公机隔离发布目录为 `/opt/ppci-release-fateboard-host-20261103.VM2TMkBk`，内含 `host-board-verification.txt`（SHA-256 `8adfeb69522c5fde5f80b7070059eabdc7831f80a47a9319aba4ed9c8eafa6cc`）。该目录内发布时的脚本可直接执行 `bash deploy_fateboard_host.sh verify` 复核上述历史任务；`bash deploy_fateboard_host.sh rollback` 只删除新建的 Host Board 容器，保留发布文件和凭据。

### 部署到另一台已准备好的 Linux

前置条件：Docker 里已有可运行的 Host Flow（加入一个可通过容器名解析的 Docker 网络）和带字符串机构 ID 补丁的 Guest FATEBoard 2.1.0 镜像/容器布局。把仓库中的 `deploy_fateboard_host.sh` 和 `CheckFateboardDetails.java` 放在同一目录，以管理员身份运行。例如使用目标机器自己的内网地址和容器名：

```bash
export PPCI_FATE_HOST_BOARD_BIND=192.168.31.49
export PPCI_FATE_HOST_BOARD_NETWORK=kuscia-exchange
export PPCI_FATE_GUEST_BOARD_CONTAINER=fateboard-native-e2e
export PPCI_FATE_HOST_FLOW_CONTAINER=fate2-flow-host-e2e
bash deploy_fateboard_host.sh install
```

未设监听地址时只绑定 `127.0.0.1`。可另设 `PPCI_FATE_HOST_BOARD_PORT`（默认 `19384`）、`PPCI_FATE_HOST_FLOW_PORT`（容器端口，默认 `9380`）、`PPCI_FATE_HOST_BOARD_CONTAINER` 和 `PPCI_FATE_HOST_BOARD_STATE_DIR`；默认容器和目录分别为 `fateboard-host-native-e2e`、`/var/lib/ppci/fateboard-host`。如果目标使用自行构建、已核验过的兼容补丁 JAR，通过 `PPCI_FATE_BOARD_JAR_SHA256` 提供可信发布件的 SHA-256。首次安装在目标机器生成独立账号，凭据文件保存在状态目录下，不需要办公机凭据。

使用相同环境变量运行 `bash deploy_fateboard_host.sh verify` 检查入口和 Host Flow；如果目标已有公开 PSI 任务，可附 `JOB_ID HOST_PARTY_ID PSI_ROWS [GUEST_PARTY_ID]` 核对已登录的任务、DAG、结果行数和可选的 Guest 隔离。`rollback` 使用相同容器名和状态目录，只删除本脚本标记的 Host Board，保留 Flow、作业和凭据。
