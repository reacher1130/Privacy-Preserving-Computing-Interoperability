# 办公定制 requester 元信息兼容修复（2026-11-02）

原生管理恢复后，统一平台真实提交“办公回归-审批恢复-20261102”时，定制 requester 在发布前返回：`failed to get file extra info: json: cannot unmarshal object into Go value of type []*models.MetaInfo`。链上任务总数仍为 21，同名任务为 0；本次失败没有创建任务或文件授权申请。

## 根因与修复

既有公开 Boston 两文件的 Ext 是上游对象格式 `{fileType,features,totalRows}`；办公定制版本仅解析 `MetaInfo[]`。修复源码来自服务器真实 `shared-exchange-Connectivity/PaddleDTX/dai`，未用 stock CLI 替换定制协议。

`paddledtx-file-metadata.patch` 增加一个标准库列名解析函数，共享给 requester 参数校验及 executor 现有元信息调用点。它兼容两格式、保持列名顺序，拒绝空/畸形元信息、空列、重复列、逗号/换行/NUL 列名。不改文件、标签、执行器在线与健康、密钥、现有授权和过期授权校验，不更改 protobuf/合约序列化。

原文件及元信息保留：

- `59ccdf91-f7c2-42c8-9be0-dd41a429d810`，`public_boston_A`。
- `1d6812b2-74a0-48ab-9496-14ccb8a8b7e4`，`public_boston_B`，包含训练标签 `MEDV`。

共享解析的两格式等价与非法输入专项测试通过；executor/handler 编译通过；custom requester 使用既有 vendor 离线构建成功。只读调用真实 `CheckPublishTaskOptions` 对上述两文件完成全部校验，返回两个参与方，标签方 `[false,true]`；空私钥及不存在 PSI 列均被原校验拒绝，未调用 Publish。

## 发布与回退

脚本：`NewProject/scripts/install_paddledtx_requester.py`。仅在办公 Linux 运行，固定使用独立 `/opt/ppci-build/paddledtx-requester`，保留原始 legacy 源码。它检查已知原 CLI 摘要，将原二进制保存在服务器后，原子替换两 executor 的 `/home/requester-cli-demo`；不重启 executor，不修改配置、身份、旧文件 metadata 或合约。

已核对运行中 Alice Java 进程明确设置 `PADDLEDTX_REQUESTER_BINARY=/home/requester-cli-demo`；没有替换成另一个 stock/current 接口。两 executor 替换前后 21 个既有 taskIDs 集合完全一致。

新二进制：22,978,744 字节，SHA256 `ed8b6d1e474d06360ad35f778293e8e803eb444baaad6ba891f288e267a92064`。

原二进制 SHA256：`8a63fd378401c975f43a8758e5aca520d4f640bc8c6c1fc1945b8c2f4191ee1a`。

服务器目录 `/var/backups/ppci/office-recovery-20261102/requester-tools` 包含原二进制（每节点一份）、源码摘要、补丁、候选二进制、只读校验源码/结果与 `requester-deployment.json`。构建日志为 `/var/log/ppci/paddledtx-requester-build-20261102.log`。

需要回退时，对指定节点将对应 `executorN.node.com.requester-cli-demo.before` 复制到容器内另一个临时路径，核对上述原摘要、恢复可执行权限后原子移动到 `/home/requester-cli-demo`；不要替换账本、配置或数据目录。部署脚本自身在二进制/任务列表核对失败时恢复该节点原二进制。

现有迁移镜像保留不变，修复位于容器可写层，普通重启后保留；如果从旧迁移镜像重建 executor，必须重跑该安装脚本。

本记录只证明源码兼容、构建、只读参数校验及 CLI 发布完成；后续须从真实页面使用原公开文件新建唯一任务，按该 taskID 批准对应文件申请并验证计算终态，不能将本次替换本身写成训练验收。
