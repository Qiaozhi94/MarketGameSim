# 安全策略

## 报告漏洞

请**不要**在公开 issue、PR 或讨论区披露漏洞细节。

使用 GitHub 私密漏洞报告：仓库 **Security → Report a vulnerability**
（[直达链接](https://github.com/Qiaozhi94/MarketGameSim/security/advisories/new)）。
请附上影响范围、复现步骤和涉及的提交或文件。维护者会在 7 天内回复。

## 支持范围

只维护 `main` 分支的最新状态；历史版本与里程碑不单独发布安全修复。

## 密钥与对话归档

- 密钥、令牌、`.env*` 永不入库。
- `conversations/` 等归档提交前必须通过 `python tools/check_secrets.py`
  （已接入 `python tools/verify.py` 与 CI），零命中才允许提交。
- 若发现已入库的密钥：先在提供方**作废并轮换**，再清理历史；仅删除文件不算修复。
