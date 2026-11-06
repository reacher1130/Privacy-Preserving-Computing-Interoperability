# 原生链桨签名下载修复（2026-11-02）

原生管理已能真实登录并查看公开数据详情，但数据/meta 下载仍是直接 `<a href>`，不会发送签名；任务列表同样如此。任务详情另有两个按钮始终下载硬编码的公开 `predict.csv`，不能代表当前任务结果。

已用原 Axios 实例及既有签名拦截器请求 Blob，签名保留在请求头，不放入 URL。数据、meta、任务列表与详情均调用真实对应 API；任务详情删除两个静态假结果按钮，只对已完成预测/PSI 任务提供真实结果下载。算法原有签名请求也复用同一个文件保存 helper。

成功文件保留原文件名并在保存后清理 ObjectURL。HTTP 200 的 JSON 业务错误仅在无附件标志且符合 `{code,msg|message,data}` 错误 envelope 时拒绝，提示真实错误；不会仅因 MIME 是 JSON 而拒绝合法文件。带附件标志的合法 JSON 即使内容恰似 envelope 也保留。

## 验证和发布

- 使用已有 TypeScript 与 Node 标准库自检，4 项通过：成功文件名/URL 清理、JSON 错误不创建文件、合法 JSON 保留、浏览器保存失败仍清理。
- 正式 `npm run build` 成功，构建错误为 0；未为本次小修重构旧全量 ESLint。
- 在 `/opt/ppci-build/dtx-native-ui` 隔离安装锁定依赖、构建，未在运行目录执行 Webpack 的 `output.clean`。
- 原源码变更文件和完整 native dist 已备份，发布新资产后原子切换 index；26 个旧 hashed 资源均保留且摘要未变。
- 实际 18511 返回的新 index 摘要与候选一致，三份新 JS 均 HTTP 200，正常登录开关仍为 false。未改管理后台、数据库、签名协议或下载鉴权。

新 index SHA256：`048fab6329ea112d4d390c85bc235c3c2cb9948a337eb69db1135853fb7b37ef`。

补丁 SHA256：`81e1b0f213a6d352a48224c925426467a7bbccf7ebf538572b53be35fbb55069`。

主任务已在真实 p5 登录会话中点击管理记录 `id=1` 的 `public-four-rows` 两条下载链接，均收到浏览器 download 事件且 `failure=null`。CSV 为 25 字节，SHA256 `bc2c9101b48d26cae3359863833f4dfac47d7ab73cc1f34dddf502c7976dd2ef`，解析四行 `id/x` 与提交 fixture 一致；meta 为 48 字节，SHA256 `494964f11e41ee05f92b77c18fada3f76dd3ef45cdf976c55d60cf9122ad8633`，内容为 `id/int`、`x/float` 两列元信息。此项为真实浏览器下载验收，独立于生产构建和 HTTP 资源探测。

## 可复现与回退

根仓交付：

- `NewProject/scripts/patches/paddledtx-native-download.patch`：9 处 source/test 文件的公开源码差异，legacy 前端不整目录导入 Git。
- `NewProject/scripts/install_paddledtx_native_ui.py`：应用补丁、锁定依赖、4 项自检、生产构建、备份及原子发布。只恢复这份原生前端，不重跑 manager 安装。

在办公服务器运行该脚本即可重建发布。`--publish-built` 只接受与 `verified-build.json` 绑定的已验证补丁和 index。它不删除旧 hashed 资源。

服务器材料：

    /var/backups/ppci/office-recovery-20261102/native-download-tools/native-download-release.json
    /var/backups/ppci/office-recovery-20261102/native-download-tools/verified-build.json
    /var/backups/ppci/office-recovery-20261102/native-download-tools/before-download-publish/native-dist.tar.gz
    /var/backups/ppci/office-recovery-20261102/native-download-tools/before-download-publish/native-source.tar.gz
    /var/log/ppci/dtx-native-ui-build-20261102.log
    /var/log/ppci/regression-20261102/native-download-build.json

回退只需从上述 dist 备份提取 `build/static/unicom-dtx/page/index.html`，恢复其文件权限后在同目录原子替换当前 index；旧 JS/CSS 均保留，无需重建容器或覆盖数据库。需要回退源码时，先在 legacy dtx-fe 根目录对该补丁执行 `git apply --reverse --check`，检查通过后再反向应用；出现源码漂移时保留现状并人工核对。不要解压整份备份覆盖后续新状态。

实现代理没有操作 Ego、读取管理员凭据或导出浏览器私钥；浏览器最终 CSV/meta 验收由主任务完成。任务结果和算法没有可用真实记录，本次只修正相应源码调用并通过自检/生产构建，不宣称其浏览器下载验收通过。
