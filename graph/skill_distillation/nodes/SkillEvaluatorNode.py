"""Skill 文件评测节点。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from graph.common.base import AgentNode
from graph.common.utils import json_dumps


class SkillEvaluationDecisionInput(BaseModel):
    """Skill 评测人的路由决策。"""

    action: str = Field(description="只能填写：继续完善 或 保存文件。其他内容会默认按 保存文件 处理。")


class SkillEvaluatorNode(AgentNode):
    """评测当前候选 Skill 文件是否可以保存。"""

    name = "skill_evaluator"
    title = "Skill 评测人"
    description = "评测候选 Skill 文件质量，并决定继续完善还是保存文件。"
    system_prompt = """
你是 Skill 评测人。你负责判断当前候选 Skill 文件是否适合作为长期可复用的场景规则保存。

请用中文自然语言输出评测意见，不要强制输出 JSON。
你必须调用 choose_skill_evaluation_action 工具给出路由决策。

评测重点：
1. 是否沉淀了可复用规则，而不是复述本次报告。
2. 是否符合当前 skill_type 的文件目标。
3. 是否有明确适用条件、降级策略、证据边界或写作约束。
4. 是否过度绑定具体表名、文件路径、任务 ID 或本次具体数值。
5. 是否和参考 Skill 文件的结构、粒度、语气大体一致。

如果明显需要重写、补充或泛化，请选择“继续完善”。
如果已经可以作为候选文件保存，请选择“保存文件”。
""".strip()
    temperature = 0.1
    use_stream = True

    def __init__(self) -> None:
        """初始化评测节点并准备默认决策。"""
        super().__init__()
        self.evaluator_decision = "accept"

    def choose_skill_evaluation_action(self, action: str) -> Dict[str, str]:
        """记录 Skill 评测路由决策。"""
        normalized = (action or "").strip()
        if normalized == "继续完善":
            self.evaluator_decision = "revise"
        elif normalized == "保存文件":
            self.evaluator_decision = "accept"
        else:
            self.evaluator_decision = "accept"
        return {
            "evaluator_decision": self.evaluator_decision,
            "message": "已记录 Skill 评测路由决策。",
        }

    async def choose_skill_evaluation_action_async(self, action: str) -> Dict[str, str]:
        """异步记录 Skill 评测路由决策。"""
        return self.choose_skill_evaluation_action(action)

    def build_decision_tool(self) -> StructuredTool:
        """创建供评测人选择下一步动作的工具。"""
        return StructuredTool.from_function(
            func=self.choose_skill_evaluation_action,
            coroutine=self.choose_skill_evaluation_action_async,
            name="choose_skill_evaluation_action",
            description=(
                "选择当前候选 Skill 文件的下一步。"
                "如果需要打回继续分析和重写，action 传入：继续完善。"
                "如果可以保存当前文件，action 传入：保存文件。"
            ),
            args_schema=SkillEvaluationDecisionInput,
        )

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """评测当前 Markdown 内容并更新路由字段。"""
        self.evaluator_decision = "accept"
        self.tools = [self.build_decision_tool()]
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        message = (raw_output or "").strip()
        if not message:
            raise ValueError("SkillEvaluatorNode 没有返回有效评测意见。")

        current_round = int(state.get("round_index") or 1)
        max_rounds = int(state.get("max_rounds") or 3)
        decision = self.evaluator_decision or "accept"
        if decision == "revise" and current_round >= max_rounds:
            decision = "max_rounds_reached"

        score = self.extract_score(message)
        revision_history = list(state.get("revision_history", []))
        revision_history.append(
            {
                "round": current_round,
                "decision": decision,
                "score": score,
                "message": message,
            }
        )

        output: Dict[str, Any] = {
            "evaluation_message": message,
            "evaluation_result": {
                "round": current_round,
                "decision": decision,
                "score": score,
                "message": message,
            },
            "evaluator_decision": decision,
            "final_score": score,
            "revision_history": revision_history,
            "status": "succeeded" if decision != "revise" else "running",
        }
        if decision == "revise":
            output["round_index"] = current_round + 1
        return output

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造 Skill 评测 prompt。"""
        return f"""
当前正在评测的 Skill 文件类型：
{state.get("skill_type", "")}

目标文件名：
{state.get("file_name", "")}

当前迭代轮次：
{state.get("round_index", 1)} / {state.get("max_rounds", 3)}

本文件写作规格：
{json_dumps(state.get("artifact_spec", {}))}

本次 Skill 沉淀的统一场景方向：
{state.get("scene_direction", "")}

场景分析师给出的沉淀方向：
{state.get("scene_mining_message", "")}

候选 Markdown 文件内容：
{state.get("markdown_content", "")}

同类型参考 Skill 文件内容：
{state.get("reference_skill_content", "")}

请先评测候选文件质量，再调用 choose_skill_evaluation_action。
如果选择“继续完善”，评测意见必须写清楚要补充、删除、泛化或重写什么。
如果选择“保存文件”，评测意见必须说明为什么可以保存。
""".strip()

    def extract_score(self, text: str) -> Optional[float]:
        """从自然语言评测中尽量提取分数。"""
        patterns = [
            r"(?:评分|分数|得分)[:：]?\s*(\d+(?:\.\d+)?)",
            r"(\d+(?:\.\d+)?)\s*/\s*100",
        ]
        for pattern in patterns:
            match = re.search(pattern, text or "")
            if not match:
                continue
            try:
                value = float(match.group(1))
            except ValueError:
                continue
            return max(0.0, min(100.0, value))
        return None

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成节点摘要。"""
        return output.get("evaluation_message", "") or "Skill 文件评测完成。"
