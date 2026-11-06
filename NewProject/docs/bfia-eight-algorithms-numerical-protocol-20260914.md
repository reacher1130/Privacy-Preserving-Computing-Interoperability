# BFIA 八算法数值与协议日志验收（2026-09-14）

现有链桨合约为 **联通定制的合并版 paddlempc**。八个原生 BFIA 算法已在办公服务器完成本轮公开样例数值与协议流程验收，并接入默认测试入口。

## 合约来源

部署记录 `paddledtx-unicom-local-deployment-20260905.md` 指向 `privacy-computing-interconnectivity/shared-exchange-Connectivity/PaddleDTX`。该版本将 XDB 文件授权与 DAI 任务能力合并进 XChain native `paddlempc`。

运行容器 `xchain1.node.com`，镜像 `ppci-migration/xchain1-node-com:20260908`；合约 `/home/work/xchain/paddlempc` 的 SHA256 为 `bbb0d34b6593a6d4df8370f5db6b61394f07911fcee237f592580eb19f71018e`。

定制源码的 `PublishFLTaskOptions.FLTask` 为 `[]byte`，使用 protobuf 序列化任务；官方目录对应字段为结构化 `FLTask`。部署记录、接口行为和运行文件共同支持定制版判断。二进制未携带可直接对应的 Git commit，不作字节级可复现溯源声明。本轮未修改合约。

## 最终数值结果

C++ 正式运行：`office-final-20260914`；Python 正式运行：`office-verified-20260914`。均来自办公服务器实际双方进程，非模拟成功结果。

| 算法 | 数值验收结果 | 流程 |
| --- | --- | --- |
| ECDH-PSI | 128 个交集 ID 与集合参考精确一致 | PASS |
| SS-LR | 16 个参数不再全零；同参数 SGD 最大误差 0.00001044 | PASS |
| SGB | 569 条概率，双方一致；独立重算训练样例 AUC 0.9942920564 | PASS |
| SS-XGB | 256 条概率；同参数明文计算最大误差 0.00068045；保存模型复算差异 0.00072332 | PASS |
| SS-Pearson | 15×15 矩阵；NumPy 参考最大误差 0.00035477 | PASS |
| SS-VIF | 15 个 VIF；相关矩阵逆对角线参考最大误差 0.00172339 | PASS |
| HE-WOE | 30 个特征、300 个分箱；计数、WOE、IV 最大误差 0 | PASS |
| SS-Compare | Alice x1 > Bob x11，256 行精确一致 | PASS |

定点验收容差：LR 默认轮数 0.00002、多轮 0.002；XGB 0.004；Pearson 0.01；VIF 0.03。表中实际误差均远低于统计/树模型的容差。采用概率截断，重复运行的末位数值可能略有差异。

扩展验收：LR 学习率 0.1、10 轮最大误差 0.00008576；SS-XGB 3 轮最大误差 0.00066978，保存模型复算差异 0.00078634。Pearson、VIF、Compare 指定 rank 0 后，仅 Bob 有明文结果，Alice 不生成明文文件。双方使用不兼容 SS 协议时，收到非成功握手响应，均在计算前失败。份额精度、缺失握手、握手拒绝三个针对性回归测试通过。

## 修复内容

- LR：先平均梯度再乘学习率，避免 `0.0001 / 128` 在 18 位定点精度下归零；参数与预测分数以精确整数环份额保存。
- Pearson/VIF：使用正确的倒数平方根；VIF 的单位矩阵使用公开常量，按总体方差标准化对应的样本数缩放；先模加重构份额，再解码明文。
- SS-XGB：按双方全部选定特征计算，安全直方图分裂、逐树累加并应用学习率，输出逻辑目标概率。保存模型包含密态分裂标识、叶权重、网格范围及公开格式元数据，并经独立复算验证。当前网格为等宽直方图，非分位点草图；不支持的列采样等参数明确拒绝。
- 特征列选择在真实握手模式下生效。参考计算按实际 rank 排序：当前 Bob=0、Alice=1，不假定 Alice 在前。
- Compare 真正执行双列比较，按协商接收方输出；握手失败不再继续计算或输出成功标志。

公开验收数据为合成 CSV 与 sklearn breast cancer 数据。LR 默认仍只有 1 轮且学习率很小；非零参数不等于训练充分。SGB AUC 为训练样例指标，不是泛化准确率。

## 详细日志与 BFIA 流程

协议依据是项目采用的 `interconnection/interconnection/handshake/entry.proto` 和对应算法、安全算子、密码协议族及 IO protobuf。每个算法保留双方原始日志，并自动生成 `protocol-events.jsonl`、`protocol-trace.md`、`protocol-validation.json` 和独立的 `numerical-validation.json`。

流程为：初始化/真实端点 → 数据准备 → 主动方请求 → 被动方协商与响应 → 主动方接受 → 安全计算 → 结果输出 → 消息排空/退出。记录任务与追踪 ID、角色/rank、时间与序号、完整公开握手参数、训练轮次、输出类型与接收方、传输统计和退出状态。Python 按消息字节数及 SHA256 逐条关联收发；C++ 对齐双方请求/响应参数并保留 YACL 传输统计，未宣称逐条追踪所有底层计算消息。日志不主动输出消息载荷、私钥或原始私有样本。

SGB 696 个结构化事件、342 次发送/接收一一匹配；HE-WOE 34 个事件、11 次发送/接收一一匹配。C++ 六算法分别有 24、30、30、28、28、26 个结构化流程事件，另保留原始算法日志中的详细计算记录。

C++ 使用真实双容器 BFIA 黑盒链路和本地转发器，禁止建立失败后自动退回白盒；测试使用 TrustedFirstParty 三元组。该结论是当前实现的双方流程与数值验收，不等同于第三方平台互操作认证或生产安全性认证。

## 办公入口与证据位置

服务器：`ssh -p 2222 root@192.168.45.101`。

运行八算法并自动检查流程、数值：

    PATH=/opt/ppci-tools/rg:$PATH bash /opt/ppci-source/NewProject/scripts/linux-migration/algorithms.sh all

将 `all` 改为 `cpp` 或 `python` 可分组运行。每次默认产生新的运行 ID。普通默认测试入口已选择 `ppci/bfia-cpp:numerics-20260914-v2`；若调用者显式指定 `BFIA_CPP_IMAGE`，该指定优先。

最终原始日志与检查产物（服务器路径）：

- `/opt/ppci/NewProject/secretflow/bfia/results/cpp/office-final-20260914/`
- `/opt/ppci/NewProject/secretflow/bfia/results/python/office-verified-20260914/`
- 扩展测试：`/opt/ppci-bfia-audit/secretflow/bfia/results/cpp/numerics-multiround-20260914/`、`numerics-model-20260914/`、`numerics-recipient-20260914/`、`numerics-refusal-20260914/`。

`numerics-refusal-20260914` 的普通协议检查故意为 FAIL，`boundary-validation.json` 为 PASS，表示成功验证了预期拒绝，不能改写成普通执行成功。

## 版本与回滚

本地独立工作树 `.local-backups/bfia-audit-work`，分支 `codex/bfia-numerics-20260914`，基线 `32c83ef56ffbc29cba86ad5af6b755a040020eb1`。未提交、推送或合并；原本地 secretflow 工作树保持不变。办公 source/runtime 已安装本轮 36 个变更文件及默认入口调整。

最终镜像 ID：`sha256:4630530465e396bc8238c9ece5685f87e3461b3327aac31d7610ba6252dc377f`；二进制 SHA256：`bae5160e4f794a9ec0337e707efae327d0354e0be235b8ebe67ec439251c7e00`。

备份 `/var/backups/ppci/bfia-numerics-20260914/` 包含原文件、逐文件哈希清单和 `rollback.py`。回滚脚本先检查部署后文件未被他人更改，再恢复原文件和原入口；旧 home 镜像保留。脚本已准备并检查，未执行破坏当前验收版本的回滚操作。

完整日志仍保留在办公服务器。自动审批拒绝向本机复制日志，需用户明确批准具体归档文件及本机目的地后才能下载。

服务器证据包：`/opt/ppci-bfia-audit/evidence/bfia-eight-algorithms-20260914.tar.gz`，1,330,490 字节，252 个产物文件（另附 README 和清单），SHA256 `99539482153c6261fa23a62214c8e6e95f19061fa99643b3ef44a0627f4f508d`。未包含 `.env` 或容器标识文件，未下载到本机。

最终部署清单 74 项文件哈希与备份存在性核对通过；临时 C++ 测试容器为 0。办公绑定地址 `http://192.168.45.101:18101/edge?ownerId=alice` 返回 HTTP 200，仅表示本轮可达性检查，未重复浏览器业务验收。全机观察到 29 个 Up、5 个 Restarting 容器，因此本报告不宣称全平台所有容器健康。


## 本地归档更新

2026-09-14 用户已明确批准指定证据包下载到当前项目 `.local-backups/bfia-numerics-20260914/`。下载及解压完成，包摘要和 252 项文件清单全部校验通过。前文“未下载/待授权”记录为历史状态，已由本次完成状态取代。入口见项目内 `.local-backups/bfia-numerics-20260914/README.md`。
