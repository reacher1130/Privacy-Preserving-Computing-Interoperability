---
status: in-progress
created: '2026-11-09'
tags: []
priority: medium
created_at: '2026-11-09T03:39:01.236Z'
updated_at: '2026-11-09T03:39:02.149Z'
transitions:
  - status: in-progress
    at: '2026-11-09T03:39:01.463Z'
depends_on:
  - 008-bfia-suite-in-platform
  - 011-portable-full-deployment
  - 013-core-layout-cleanup
---

# 八算法镜像交付与Kuscia一键运行

## Overview

承接[八算法平台入口](../008-bfia-suite-in-platform/README.md)、[免编译部署](../011-portable-full-deployment/README.md)和[核心布局](../013-core-layout-cleanup/README.md)，将公开样本验证封装为可拉取的自包含镜像，网页仍可一键取得真实结果、数值/协议校验和双方日志；新机器默认拉取已发布程序与镜像，无需编译。

## Design

- 用户最新约束：构建、下载大文件、容器和实测全部在公司Anolis8.10 amd64服务器，本机只编辑代码/轻量检查；允许访问服务器，保留现有服务与数据。
- suite镜像包含两项Python源码及依赖、六项C++预编译引擎、公开样本和校验器，无宿主源码挂载或容器内Docker。C++私有Debian加载器隔离其glibc与Anolis Python环境。
- Kuscia通过新AppImage/KusciaJob运行suite；固定执行器保持UUID、报告路径和后端权限接口，任务产物有界验证后落私有结果目录，保留实际执行日志。
- 镜像发布使用自有仓库固定版本和摘要；只发布干净源码构建产物，不能将现有office迁移镜像/容器提交公开，因为可能带业务数据/身份。
- 根入口默认下载固定摘要的发布清单、程序和运行镜像；build保留维护者显式编译路径，runtime bootstrap不安装编译工具。

## Plan

- [ ] 自包含镜像、受控构建上下文和有界产物协议。
- [ ] Kuscia任务执行器与现有网页接口接通。
- [ ] 干净程序/镜像发布、匿名拉取验证及根免编译部署。
- [ ] 公司服务器真实八算法、日志与结果验收，记录镜像/源码/运行身份。

## Test

- [ ] 镜像内无源码挂载/Docker socket执行8项，数值及协议全部通过。
- [ ] Kuscia任务真实创建/结束，网页发起可刷新、查看双方日志及下载报告。
- [ ] 无仓库凭据拉取已发布摘要；空白运行环境部署不调用Go/Maven/Node/Bazel/C++编译。
- [ ] 保留已有数据库、账本、身份、任务及非本轮容器；异常可恢复旧执行器。

## Notes

初始只读盘点：服务器30GiB内存、约18GiB可用、116GB可用磁盘；现有Kuscia无Running任务。系统python3是3.6，已有python3.11，运行依赖必须匹配实际解释器。已有Python依赖镜像与C++镜像glibc不兼容，私有加载器方案已在临时受限容器验证，不改宿主glibc。
