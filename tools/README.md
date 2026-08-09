# tools —— 校验与工具脚本

本目录存放验证与辅助脚本。**公开验证唯一入口**是 [`verify.py`](verify.py)：

```bash
python tools/verify.py
```

按固定顺序运行：真源校验 → 规格生命周期校验 → pytest → ruff check → ruff format
check。失败即返回非零。

## 校验脚本

| 脚本 | 用途 | 是否公开入口 |
|---|---|---|
| [`verify.py`](verify.py) | 本地统一验证入口（唯一公开入口） | 是 |
| [`validate_contract_sources.py`](validate_contract_sources.py) | 事件 Schema / report artifacts / traceability 真源自校验 | 否（verify 调用） |
| [`validate_spec_lifecycle.py`](validate_spec_lifecycle.py) | 规格生命周期：frontmatter、状态、前置、链接、gate 门禁 | 否（verify 调用） |
| [`spec_validation.py`](spec_validation.py) | 共享规格校验纯函数（供上述两个 CLI 复用） | 否（被导入） |

## 辅助脚本

- `build_retrospective.py`、`export_conversations.py`、`determinism_probe.py`、
  `formal_calibration.py`、`run_robustness_demo.py`：实验与分析辅助，按需运行。

## 校验职责边界

- `spec_validation.py` 是 owner/path/exit 判据的**唯一共享实现**；新校验规则应加在
  共享模块并补变异测试，不在 CLI 中另抄一份。
- 机器门只证明引用与结构自洽，语义覆盖由 review 判断。
