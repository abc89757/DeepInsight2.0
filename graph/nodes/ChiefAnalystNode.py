"""首席分析师节点。

这个文件定义 ChiefAnalystNode，用来控制多轮分析循环：决定继续分析还是进入报告生成。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps, parse_json_object


class ChiefAnalystNode(AgentNode):
    """负责控制分析循环并指定下一轮分析目标的 AgentNode。"""

    name = "chief_analyst"
    title = "首席分析师"
    description = "决定本轮分析目标，或判断是否可以生成报告。"
    system_prompt = "你是首席数据分析师。你只输出 JSON，不输出解释。"
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """决定继续请求数据证据，还是进入报告生成。

        输入:
            state: 当前图状态；通常包含用户问题、Skill、当前轮次、最大轮次和
                已沉淀的 `analysis_rounds`。

        输出:
            包含 `chief_decision`、`director_action` 的状态更新；如果需要继续分析，
            还会包含 `analysis_goal`、递增后的 `analysis_round`，以及追加后的
            `chief_decision_history`。
        """
        current_round = int(state.get("analysis_round") or 0)
        max_rounds = int(state.get("max_analysis_rounds") or 3)
        analysis_rounds = list(state.get("analysis_rounds", []))

        if current_round >= max_rounds:
            decision = {
                "round": current_round,
                "action": "ready_for_report",
                "analysis_goal": "",
                "reason": f"已达到最大分析轮数 {max_rounds}，进入报告生成。",
            }
            return {
                "chief_decision": decision,
                "director_action": "ready_for_report",
                "chief_decision_history": list(state.get("chief_decision_history", [])) + [decision],
            }

        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        decision = parse_json_object(raw_output)
        action = decision.get("action")
        if action not in {"need_evidence", "ready_for_report"}:
            action = "ready_for_report" if analysis_rounds else "need_evidence"
        if action == "ready_for_report" and not analysis_rounds:
            action = "need_evidence"

        analysis_goal = str(decision.get("analysis_goal") or "").strip()
        if action == "need_evidence" and not analysis_goal:
            analysis_goal = f"围绕用户问题进行第 {current_round + 1} 轮数据证据分析"

        next_round = current_round + 1 if action == "need_evidence" else current_round
        decision = {
            "round": next_round,
            "action": action,
            "analysis_goal": analysis_goal,
            "reason": decision.get("reason") or "",
            "expected_evidence": decision.get("expected_evidence") or "",
        }

        output = {
            "chief_decision": decision,
            "director_action": action,
            "chief_decision_history": list(state.get("chief_decision_history", [])) + [decision],
        }
        if action == "need_evidence":
            output["analysis_goal"] = analysis_goal
            output["analysis_round"] = next_round
        return output

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造首席分析师决策 prompt。

        输入:
            state: 当前图状态；包含用户问题、Skill 概览和已完成的 `analysis_rounds`。

        输出:
            要求模型选择 `need_evidence` 或 `ready_for_report` 的 prompt 字符串。
        """
        skill = state.get("skill") or {}
        return f"""
你负责控制一个多轮数据分析流程。请根据用户问题、Skill 和已完成的分析轮次，决定下一步：
- 如果还需要新的数据证据，输出 need_evidence，并给出这一轮分析目标。
- 如果已有分析轮次足以生成报告，输出 ready_for_report。

用户问题：
{state["question"]}

Skill 概览：
{skill.get("overview", "")}

已完成分析轮次 analysis_rounds：
{json_dumps(state.get("analysis_rounds", []))}

要求：
1. 只输出 JSON，不要输出 Markdown 或解释。
2. JSON 字符串内部如果需要引用字段值、标签或原文，请使用单引号或中文引号，不要使用英文双引号；如果必须使用英文双引号，必须写成转义形式 `\"`。

只输出 JSON：
{{
  "action": "need_evidence 或 ready_for_report",
  "analysis_goal": "本轮要验证或分析的目标",
  "expected_evidence": "希望得到什么证据",
  "reason": "为什么这样决策"
}}
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用配置好的 LLM 完成分析控制决策。

        输入:
            prompt: `build_prompt` 生成的 prompt。
            state: 当前图状态；此处主要用于保持 AgentNode 接口一致。

        输出:
            模型返回的原始文本。
        """
        return self.llm_client.complete(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=self.temperature,
            tools=self.tools,
            stream=self.stream,
            timeout=self.timeout,
        )

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的首席分析师决策摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        if output.get("director_action") == "ready_for_report":
            return "首席分析师判断可以生成报告。"
        return f"本轮分析目标：{output.get('analysis_goal')}"
