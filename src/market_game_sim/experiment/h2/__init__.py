"""H2 双轨实验（AI 机制基线 + 所有者 N-of-1）。

本包只服务 0.3.1，与既有的两类 protocol 严格分开：

* ``experiment/protocol.py``：v0.1.5 的三区运行约束（校准/冻结验证/信念实验）。
* ``experiment/stress_protocol.py``：外生压力合同。
* ``experiment/h2/protocol.py``（本包）：H2 的研究设计预注册与内容寻址冻结。

三者的 schema、错误码和 evidence guard 不得互相冒充——共享工具可以抽取复用，
但一份协议只能由拥有它的模块校验。
"""

from __future__ import annotations
