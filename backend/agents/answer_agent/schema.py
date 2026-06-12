"""
answer_agent 判断对象 schema。

- `HuidaPan`：回答主判断维度，由 AnswerAgent 自己产出，service 只做透传。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HuidaPan:
    """
    answer 回答策略主判断（由 main 协作维度 + middle 材料维度推出，不绑用户例句）。

    - `da_fengshi`：zhijie / baoshou / fenkai —— 本轮对外回答的整体姿态。
    - `jiegou_mode`：short / sections / qa —— 文本组织结构。
    - `baoshou_level`：0~1，越高越保守（落入 hint 后影响生成端语气）。
    - `lane` / `primary_path`：answer 侧使用的路径标签；turn-level 主路径以 chat 出口层为准。
    """

    da_fengshi: str
    jiegou_mode: str
    baoshou_level: float
    lane: str
    primary_path: str
