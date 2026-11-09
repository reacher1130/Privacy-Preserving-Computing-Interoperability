# 办公链桨管理后台恢复（2026-11-02）

办公环境：`192.168.45.101`。本次补齐原生链桨管理后台，保留已有账本、文件、任务、身份与计算执行器。

## 运行结果

- 原生管理入口：`http://192.168.45.101:18511/dtx/console/`。既有 Nginx `/dtx/v1/` 代理已接通新管理端。
- 新容器：`ppci-dtx-manager`，镜像 `ppci/dtx-manager:recovery-20261102`；新数据库/账号为 `ppci_dtx`，不改已有库。
- 状态目录：`/srv/ppci/dtx-manager`。配置、上传文件、持久数据和日志独立保存；随机管理员和低权限探测账号凭据只保存在 `private/*.json`，权限 `0600`，未下载或写入 Git。
- 新增独立 XChain 原生管理合约 `data`，复用当前合约账号。部署前明确查到该合约不存在；未升级或覆盖联通定制的合并版 `paddlempc`。
- 三个正式 dataowner、三个 storage、两个 executor 保留。另五个旧 Bob 容器因 `/data/hz` 配置/密钥挂载为空反复退出，已设 `restart=no` 并停止；容器、镜像、原目录均保留。
- 原 `dtx-manager` 历史容器因旧 MySQL 地址不可达、网络失效及配置缺失而退出，保留原位。本次创建新管理库，未宣称恢复不存在的旧业务库或导入历史管理元数据。

## 实际验收

直连 `127.0.0.1:8084` 与上述原生 Nginx 代理分别通过 24 项签名 API 检查：真实前端 MD5 密码协议登录、解密签名密钥、管理员数据/模型/任务列表、低权限拒绝、匿名拒绝、密码重置保护、错误/过期/未来签名拒绝及上传目录越界拒绝。首次另创建低权限探测账号，因此首轮为 25 项。

另通过原生代理执行一条真实公开数据流程：

1. 新建目录 `mgr-1793611517`。
2. 签名上传合成四行 CSV 与元数据，建立管理记录，异步解析并持久保存至管理端本地存储，状态到 `2`。
3. 发布至 `data` 管理合约，状态到 `3`，返回非空交易 ID。
4. 通过管理 API 读取链上目录，核对资源 ID 与四行样本数。
5. 签名下载 CSV，内容与提交文件逐字节相同。

公开样例资源：`31745fce-d08e-4b8a-ba91-9f52a22147d6`，管理记录 ID `1`；发布交易 `6863e743a2482d0d2411f610a7b50cd47a2086166d0db5b796c9da49e69b957e`。CSV SHA256：`bc2c9101b48d26cae3359863833f4dfac47d7ab73cc1f34dddf502c7976dd2ef`。

此样例选择管理端支持的本地存储。未将其写成管理端 XDB 存储或跨组织授权验收。管理授权主体是组织密钥；更换同组织登录用户不能替代第二组织的申请/审批。模型/任务列表接口可用，但新管理库没有导入已有计算任务/模型记录。

样例完成后再跑 24 项权限检查仍通过，数据列表为 `1`、模型和任务列表为 `0`。最终容器为 running，自动重启次数 `0`。

## 原生网页登录缺口修复

随后实际打开原生页面时发现：菜单可进但列表报签名错误。根因是历史 dtx-fe 的 `src/public/index.html` 和实际挂载的 `build/static/unicom-dtx/page/index.html` 仍设置 `window.__DTX_DEMO_AUTH_DISABLED__ = true`。此开关同时放行匿名页面守卫，并让没有登录签名密钥的请求不发送签名；恢复后的真实管理后台正确拒绝这些请求。不能把菜单可见或此前 Go 签名 API 通过写成原生 UI 登录通过。

已先备份两份 HTML，再通过 `paddledtx-native-login.patch` 和恢复脚本的独立步骤关闭旧开关；源码模板与实际 dist 保持正常登录模式。无需重建所有前端资产、重跑管理安装、改数据库或放宽后端权限：

    python3 /opt/ppci-source/NewProject/scripts/recover_paddledtx_manager.py --native-login-only

该步骤重复运行已验证幂等；实际登录/退出路由响应均加载 `false`，匿名 API 仍返回 `SignErr`。备份/摘要记录分别为 `/var/backups/ppci/office-recovery-20261102/native-login-before/`、`native-login-deployment.json`；检查摘要为 `/var/log/ppci/regression-20261102/native-login-flag.json`。

登录路由为 `http://192.168.45.101:18511/dtx/console/login`，表单字段 `username`、`password`，输入原密码，由前端执行既有 MD5 密码协议。如需清理该应用旧会话，使用其 `/dtx/console/logout` 正常退出路由，只移除该 origin 的 `unicom_dtx_user_profile`；未清用户整个浏览器状态。管理员凭据文件保留在 `/srv/ppci/dtx-manager/private/credentials.json`；实际网页登录时仅通过 SSH 在内存中传给登录表单，未输出、下载为文件或写入 Git。

主任务随后在 Ego Lite 直连真实公司 IP，完成登录、我的数据资源、公开样例详情/两列特征统计/交易存证、我的模型资源、任务列表及存储网络页面检查。前两项空管理列表与新库数据一致；存储网络实际显示三个 storage 运行中但健康节点 0。此结果不替代尚待跨日完成的计算模型写入与预测。详见 `office-recovery-20261102/webpages.md`。

## 源码与安全修复

复用服务器原 `shared-exchange-Connectivity/dtx-manager` 及定制 PaddleDTX vendor；在 `/opt/ppci-build/dtx-manager` 独立编译，未改原始历史源码。Go 工具为 `/opt/ppci-tools/go124/go/bin/go`。修正历史未使用依赖的 vendor 清单冲突；独立管理合约复用现有 XChain SDK，离线构建，无新增下载依赖。

- `paddledtx-manager-auth.patch`：密码重置要求签名及管理员；下载执行权限校验；未知业务 API 默认拒绝；补齐权限映射；签名期限改为五分钟并拒绝明显未来时间；不记录完整请求、签名和响应。
- `paddledtx-manager-upload.patch`：安全文件名、私有目录、原子写入；创建/更新限定当前用户上传文件，拒绝符号链接及路径穿越；下载与本地资源路径同样校验。
- `paddledtx-manager-sdk-log.patch`：旧 SDK 不再输出完整默认配置。
- `paddledtx-native-login.patch`：源码模板关闭遗留免登录演示；恢复脚本同步关闭实际 dist 的同一开关。
- 鉴权、控制器权限策略、文件路径边界三个专项 Go 测试通过，管理端及原生合约均从源码构建成功。

新镜像使用 `scratch`，仅包含静态二进制、CA 和时区；只读根文件系统、移除 capabilities、不挂 Docker socket。端口仅绑定主机回环和现有前端的 Docker host-gateway，通过原生代理访问。

## 复现与保留材料

部署脚本：`NewProject/scripts/recover_paddledtx_manager.py`，仅在办公服务器执行。它要求已有变更前数据库/账本备份；存在新管理容器时拒绝覆盖。它不替代备份步骤，也不会重新生成既有链账户/节点身份。

正常检查（登录服务器，从独立管理源码目录执行）：

    cd /opt/ppci-build/dtx-manager
    GOENV=off GOPROXY=off GOTOOLCHAIN=local /opt/ppci-tools/go124/go/bin/go run -mod=vendor /opt/ppci-source/NewProject/scripts/check_paddledtx_manager.go -base-url http://192.168.45.101:18511 -probe-credentials /srv/ppci/dtx-manager/private/probe-credentials.json

增加 `-public-workflow` 会新建一份公开合成样例及链上目录，不覆盖旧数据。普通检查复用已有探测账号。

服务器备份目录：`/var/backups/ppci/office-recovery-20261102`，权限 `0700`。包含变更前容器元数据/目录状态、MySQL 逻辑备份、短暂暂停单节点后生成的 XChain1 文件快照及其挂载备份、原管理源码与必要 vendor 归档、部署版本记录及管理 API/公开样例验收 JSON。样例验收后又备份新管理库和持久状态，并更新 14 个归档文件的摘要清单。所有凭据材料留在服务器；未读取此前被审批拒绝导出的旧容器配置。账本备份未做独立还原演练。

最终 Go 二进制 SHA256：`8b6b42416b1c1bbd85b480426dadf3fc2ba5e1bf55ebaf278d61783aad263249`。原生 `data` 合约二进制 SHA256：`9ce780c2824a054fbfe9b2fd190f2f5730123e111caba450ade1889ebe0d174a`。原 `paddlempc` SHA256 仍为 `bbb0d34b6593a6d4df8370f5db6b61394f07911fcee237f592580eb19f71018e`。

初版管理容器/镜像保留为 `ppci-dtx-manager-bootstrap-20261102` / `ppci/dtx-manager:bootstrap-20261102`，停止且无自动重启。切换时数据仍在上述持久目录和独立数据库；不要删除状态目录或用旧数据库覆盖当前库。

## 验收边界

已完成上述原生网页登录和只读页面；尚未完成跨组织申请/审批、管理端 XDB 存储或管理端发起模型训练。既有前端签名协议仍未绑定 HTTP 方法/路径，旧密码存储方案也未在本次兼容恢复中更换。本轮功能与边界检查不构成生产安全认证。
