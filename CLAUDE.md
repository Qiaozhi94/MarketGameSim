# MarketGameSim 项目须知

## 提交前必须本地跑通

```bash
pytest
ruff check .
ruff format --check .
```

CI 的 `lint` job 与 `test` job 是独立的两步，`pytest` 全绿不代表 `ruff` 也会通过——
0.1.1 首次提交时就因为没跑 lint，被 CI 的 `ruff check .` 挡下 105 处违规（多数是
超长行、未清理的 import/变量）。提交前在本地跑一遍，几秒钟能挡住，不用等 CI 跑完
再回来改。

`ruff format .` 与 `ruff check . --fix` 能自动处理大部分问题（超长行、未排序/未使用
的 import 等）；剩下的（未使用变量、过宽的异常断言、废弃写法等）需要手工看一眼再改，
改完重新跑一遍上面三条确认全绿。
