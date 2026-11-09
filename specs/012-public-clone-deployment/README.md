---
status: complete
created: '2026-11-06'
tags: []
priority: medium
created_at: '2026-11-06T07:23:01.104Z'
updated_at: '2026-11-09T02:41:15.719Z'
transitions:
  - status: in-progress
    at: '2026-11-06T07:23:31.913Z'
  - status: complete
    at: '2026-11-09T02:41:15.719Z'
depends_on:
  - 011-portable-full-deployment
completed_at: '2026-11-09T02:41:15.719Z'
completed: '2026-11-09'
---

# 公开仓库与无凭据部署验证

> **Status**: ✅ Complete · **Priority**: Medium · **Created**: 2026-11-06


## Overview

承接[全量部署入口](../011-portable-full-deployment/README.md)，让另一台机器无需GitHub私有仓库权限即可取得主仓与所有固定子模块，并检查新机引导。

## Design

- 审查全部分支历史与源码快照，核对Actions/release元数据；历史Actions日志未逐条审查，不以工作区clean代替敏感信息检查。
- 五个无真实凭据的自有模块可直接公开；主仓、前端和SecretFlow原历史含访问令牌、登录口令摘要或私钥，保持私有。
- 用户已明确授权这三个仓库改名为私有归档，在原地址建立独立、无旧Git对象的脱敏公开快照，并同步本地；不能只删除HEAD文件就公开旧历史。
- 新机修复：独立JDK目录加入PATH；下载使用已安装curl并保留校验，Maven使用官方Central地址；公开CI在Ubuntu22/24无凭据递归克隆、跑测试并执行bootstrap/check。
- 本机用2CPU/4GB/12GB限额的隔离Ubuntu24 amd64验证，不动既有业务容器；磁盘不足完整全栈构建，不冒称算法或ARM整机验收。

## Plan

- [x] 主仓和15个递归模块的可见性、权限、固定commit与历史敏感内容审查。
- [x] 五个无敏感阻断子库公开；三份原库仍私有。
- [x] 验证全refs私有备份，准备主仓10字段脱敏、删除前端自动登录页及SecretFlow旧私钥/文档实值的候选。
- [x] 修复新机Java发现问题，补回归和公开克隆CI。
- [x] 用户授权私有归档/原地址重建后发布三个干净候选并同步本地工作区；原Git元数据和全refs bundle另存私有备份。
- [x] 不带凭据递归克隆，全部15个固定版本匹配，Linux bootstrap/check与Ubuntu22/24公开CI通过。

## Test

- [x] Gitleaks加人工逐项分类；公开上游测试夹具逐字节核对；实际部署凭据不发布。
- [x] 49项部署测试与3项运行状态测试通过；包含新机无系统Java发现和校验失败不覆盖已有下载的回归。
- [x] 独立Ubuntu实际bootstrap/check及公开仓库匿名递归克隆、全部52项测试通过。
- [x] [公开CI 42202219257](https://github.com/reacher1130/Privacy-Preserving-Computing-Interoperability/actions/runs/42202219257)：Ubuntu22.04和24.04两个job全部成功。
- [x] 公开快照274c831源码包生成并验证全部16,436个文件摘要；Git元数据缺席、10字段脱敏及两份敏感文件移除均验证通过。

## Notes

旧私有源码包继续保留且权限0600，不作为公开release上传。旧长期令牌、口令摘要和私钥未用于访问服务，也未在本次撤销；原历史归档必须保持私有。公开候选仅从新的Git历史开始，原记录保留在私有库及本地备份。
