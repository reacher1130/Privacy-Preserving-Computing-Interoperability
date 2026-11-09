---
status: complete
created: '2026-11-09'
tags: []
priority: medium
created_at: '2026-11-09T02:54:49.403Z'
updated_at: '2026-11-09T03:05:22.955Z'
transitions:
  - status: in-progress
    at: '2026-11-09T02:54:49.633Z'
  - status: complete
    at: '2026-11-09T03:05:22.955Z'
depends_on:
  - 011-portable-full-deployment
  - 012-public-clone-deployment
completed_at: '2026-11-09T03:05:22.955Z'
completed: '2026-11-09'
---

# 核心目录整理

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-11-09


## Overview

承接[全量部署入口](../011-portable-full-deployment/README.md)和[公开仓库](../012-public-clone-deployment/README.md)，去掉本地根目录中的旧集合及身份残留，将含核心组件的历史目录NewProject更名为platform，保留一键部署、算法和打包能力。

## Design

- 只改源码布局；已有ROOT/NewProject运行数据、证书、数据库和挂载路径保持兼容，历史验收数据不重写。
- 所有15个递归子模块版本保持不变，更新真实源码引用、Git子模块路径、CI、测试和使用说明。
- legacy六个仓含独有提交和未提交定制，连同旧节点身份、笔记，先生成私有完整归档并逐项校验，再移除原目录；不能视为无用源码直接丢弃。
- dist两份源码包、既有备份、已跟踪的构建.cache、Bob相对软链接保留。
- 本次仅本机操作，不连接或修改公司服务器。

## Plan

- [x] 完成源码目录迁移、路径引用和说明更新；保留稳定的Git子模块名称以兼容旧缓存。
- [x] 检查本机4容器的挂载、打开文件及45个可读launchd配置，候选无引用；验证私有归档并移除6个旧集合/身份/笔记根目录。
- [x] 校验15固定版本、源码包清单及部署/运行测试。

## Test

- [x] 49项部署测试及3项运行状态测试通过，新增nginx运行路径断言；相关Bash语法通过。
- [x] 私有归档29,691个条目、类型、权限、9条软链接和23,890个文件摘要均匹配；包含断链及六仓Git元数据。
- [x] source-only实际打包及16,437个文件清单校验通过，包含platform、全部固定模块及构建源码，无旧本地集合/身份/备份；无Git解包副本sync及全部52项测试通过。

## Notes

NewProject实际含9个直接子模块、FATE内5个模块，以及集成脚本/补丁/样例/文档；根PaddleDTX是另一独立核心模块。目录整理不代表新CentOS、ARM或全栈首次安装已验收。

私有归档位于.local-backups/layout-20261109，压缩前普通文件1,394,464,984字节，归档1,014,412,912字节；原dist两份源码包保持不变。没有连接公司服务器。
