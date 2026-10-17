"""0.4.2 人类扰动实验（H2-F）：owner 自由会话 artifact、同种子对照与稳定性效应量。

* ``session.py``：``PerturbationSession`` 的冻结格式、内容哈希与校验入口。

与 0.3.1 的 ``experiment/h2/`` 互不复用：那里是固定窗口的所有者轨，这里是持续市场里的
自由参与，格式与校验各由自己的模块拥有。
"""

from __future__ import annotations
