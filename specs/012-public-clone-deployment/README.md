---
status: in-progress
created: '2026-11-06'
tags: []
priority: medium
created_at: '2026-11-06T07:23:01.104Z'
updated_at: '2026-11-06T07:23:32.882Z'
transitions:
  - status: in-progress
    at: '2026-11-06T07:23:31.913Z'
depends_on:
  - 011-portable-full-deployment
---

# 公开仓库与无凭据部署验证

## Overview

承接[全量部署入口](../011-portable-full-deployment/README.md)，让另一台机器无需GitHub私有仓库权限即可取得主仓与所有固定子模块，并检查新机引导。

## Design

- 审查公开范围包括全部分支历史、源码快照与Actions/附件，不以工作区clean代替敏感信息检查。
- 五个无真实凭据的自有模块可直接公开；主仓、前端和SecretFlow原历史含访问令牌、登录口令摘要或私钥，保持私有。
- 为这三个仓库准备独立、无旧Git对象的脱敏快照；旧库保留私有归档，原地址建立公开版本的方案须经用户明确授权后执行，不能只删除HEAD文件就公开旧历史。
- 新机修复：独立JDK目录加入PATH；下载请求明确User-Agent；公开CI在Ubuntu22/24无凭据递归克隆、跑测试并执行bootstrap/check。
- 本机用2CPU/4GB/12GB限额的隔离Ubuntu24 amd64验证，不动既有业务容器；磁盘不足完整全栈构建，不冒称算法或ARM整机验收。

## Plan

- [x] 主仓和15个递归模块的可见性、权限、固定commit与历史敏感内容审查。
- [x] 五个无敏感阻断子库公开；三份原库仍私有。
- [x] 验证全refs私有备份，准备主仓10字段脱敏、删除前端自动登录页及SecretFlow旧私钥/文档实值的候选。
- [x] 修复新机Java发现问题，补回归和公开克隆CI。
- [ ] 用户授权私有归档/原地址重建后发布三个干净候选并同步本地工作区。
- [ ] 不带凭据递归克隆，检查固定版本、Linux bootstrap/check与公开CI结果。

## Test

- [x] Gitleaks加人工逐项分类；公开上游测试夹具逐字节核对；实际部署凭据不发布。
- [x] 候选48项部署测试通过；新机无系统Java发现回归通过。
- [ ] 独立Ubuntu实际bootstrap/check及公开仓库匿名递归克隆。

## Notes

旧私有源码包继续保留且权限0600，不作为公开release上传。旧长期令牌、口令摘要和私钥未用于访问服务，也未在本次撤销；原历史归档必须保持私有。公开候选仅从新的Git历史开始，原记录保留在私有库及本地备份。
