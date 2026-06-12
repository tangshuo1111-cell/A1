"""
agents 共享：agent framework runtime 基础。

设计要点：
- main / middle / answer 都通过同一个 `AgnoAgentRuntime` 执行壳产出主判断。
- 每个 agent **拥有自己的 `AgnoAgentRuntime` 子类**，以五段方法直接产出主判断核心字段。
- `MainDecision` 由 `MainAgentRuntime.panduan_main_decision(...)` 自产（`router_source="main_agent_runtime"`）。

执行链仍是三步：`prepare_frame → invoke_executor → finalize_outcome`。
- `executor` 仍可作为可选注入 hook（测试 / 未来 LLM 化），但 **默认主脑** 是 runtime 子类自身的
  `invoke_executor` 内置五段方法，而不是外部裸函数。

明确不做：
- **不**调 LLM、**不**做策略；本壳只负责"按帧执行"。
- **不**引入 planner / critic / verifier。
- **不**做自治循环，**不**做开放 retry，**不**改 service 主脑。
"""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

# 帧编号全局自增（仅用于 trace 可读性，不参与判断）
_FRAME_COUNTER = itertools.count(1)


@dataclass(frozen=True)
class AgentPromptPack:
    """三强统一的 prompt 资产容器（角色 / 指令 / 模板 / 输出格式）。"""

    jieshe: str
    zhidao: str
    prompt_moban: str
    shuchu_geshi: str

    def role_signature(self) -> str:
        """对 prompt_pack 取一个稳定指纹；外部测试可断言 prompt 真的进入 runtime。"""
        body = "|".join((self.jieshe, self.zhidao, self.prompt_moban, self.shuchu_geshi))
        return hashlib.sha1(body.encode("utf-8")).hexdigest()[:12]

    def is_loaded(self) -> bool:
        return all(s.strip() for s in (self.jieshe, self.zhidao, self.prompt_moban, self.shuchu_geshi))


T = TypeVar("T")


@dataclass(frozen=True)
class AgentRunFrame:
    """
    一次 agent runtime 执行的"运行帧"：身份 + prompt 资产 + 输入 + 帧 ID + 角色指纹。

    内核 executor 必须接收 frame 才能产出结果，由此保证 prompt_pack **真正参与执行**，
    而不是"挂在类上当摆设"。
    """

    agent_mingzi: str
    prompt_pack: AgentPromptPack
    inputs: Mapping[str, Any]
    frame_id: str
    role_signature: str


@dataclass(frozen=True)
class AgentRunOutcome(Generic[T]):
    """runtime 执行的标准化输出：保留帧 + 结果 + 可选执行说明。"""

    frame: AgentRunFrame
    result: T
    notes: tuple[str, ...] = ()


AgentExecutor = Callable[[AgentRunFrame], T]
"""内核执行器签名：接收 frame，返回结果（必须是同步、单步；不允许循环）。"""


class AgnoAgentRuntime(Generic[T]):
    """
    agent framework runtime 基础。

    - 持有 agent 身份（`mingzi`）+ prompt 资产（`prompt_pack`）+ 可选注入执行器（`executor`）。
    - `run(**inputs)` 走三步：`prepare_frame` → `invoke_executor` → `finalize_outcome`。
    - **强 agent 形态**：每个 agent 应该子类化本类（`MainAgentRuntime` / `MiddleAgentRuntime` /
      `AnswerAgentRuntime`），在子类里以"意图识别 / 局部策略 / 主判断 / 失败边界 / 清洗约束兜底"
      五段方法直接产出主判断核心字段，并 **override `invoke_executor`** 把这五段串起来。
      外部 `executor` 注入只作为可选 hook（测试 / 未来 LLM 化），不取代子类自身的主脑。

    任何 agent 必须经过本基础的执行链才能产出主判断对象，否则就是裸函数，不算 framework runtime。
    """

    def __init__(
        self,
        *,
        mingzi: str,
        prompt_pack: AgentPromptPack,
        executor: AgentExecutor | None = None,
    ) -> None:
        if not prompt_pack.is_loaded():
            raise ValueError(
                f"agent runtime `{mingzi}` 的 prompt_pack 未完整装载（角色/指令/模板/输出格式四件不全）",
            )
        self.mingzi = mingzi
        self.prompt_pack = prompt_pack
        self._executor: AgentExecutor | None = executor

    @property
    def role_signature(self) -> str:
        return self.prompt_pack.role_signature()

    @property
    def has_injected_executor(self) -> bool:
        return self._executor is not None

    @property
    def runtime_brain_owned_by_agent(self) -> bool:
        """
        断言"主脑归属本 runtime 子类"——也就是子类是否 override 了 `invoke_executor`。

        - True ⇨ 当前 runtime 实例由它自己的子类的 `invoke_executor` 当主脑（本轮验收线）；
        - False ⇨ 仍依赖基类默认行为（即必须靠外部注入 executor 才能跑），属于"shared 壳"形态。

        只看 **类层级** 是否 override，不看运行期是否注入了 executor：注入 executor 是
        可选 hook，不影响"主脑归属"是 runtime 子类这件事。
        """
        own = type(self).__dict__.get("invoke_executor")
        return own is not None and own is not AgnoAgentRuntime.__dict__["invoke_executor"]

    def with_executor(self, executor: AgentExecutor) -> AgnoAgentRuntime[T]:
        """运行期返回一个换了 executor 的新壳；不修改原实例。"""
        clone = self.__class__.__new__(self.__class__)
        clone.mingzi = self.mingzi
        clone.prompt_pack = self.prompt_pack
        clone._executor = executor
        return clone

    def prepare_frame(self, **inputs: Any) -> AgentRunFrame:
        fid = f"{self.mingzi}#{next(_FRAME_COUNTER):06d}"
        return AgentRunFrame(
            agent_mingzi=self.mingzi,
            prompt_pack=self.prompt_pack,
            inputs=dict(inputs),
            frame_id=fid,
            role_signature=self.role_signature,
        )

    def invoke_executor(self, frame: AgentRunFrame) -> T:
        """
        默认行为：若有外部注入 executor 则调它；否则要求子类 override。

        子类（强 agent 实体）应当 override 本方法，把"意图识别 / 局部策略 / 主判断 /
        失败边界 / 清洗约束兜底"五段串起来，而 **不是** 把核心判断委托给外部裸函数。
        """
        if self._executor is None:
            raise NotImplementedError(
                f"agent runtime `{self.mingzi}` 既未注入 executor，也未在子类里 override invoke_executor",
            )
        return self._executor(frame)

    def finalize_outcome(self, frame: AgentRunFrame, result: T, *, notes: tuple[str, ...] = ()) -> AgentRunOutcome[T]:
        return AgentRunOutcome(frame=frame, result=result, notes=notes)

    def run(self, **inputs: Any) -> AgentRunOutcome[T]:
        """统一执行链：prepare_frame → invoke_executor → finalize_outcome。"""
        frame = self.prepare_frame(**inputs)
        result = self.invoke_executor(frame)
        return self.finalize_outcome(frame, result)
