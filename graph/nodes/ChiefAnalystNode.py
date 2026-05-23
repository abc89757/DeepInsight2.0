"""首席分析师节点。

这个文件定义 ChiefAnalystNode，用来控制多轮分析循环：决定继续分析还是进入报告生成。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps


READY_FOR_REPORT_FLAG = "READY_FOR_REPORT"


class ChiefAnalystNode(AgentNode):
    """负责控制分析循环并指定下一轮分析目标的 AgentNode。"""

    name = "chief_analyst"
    title = "首席分析师"
    description = "决定本轮分析目标，或判断是否可以生成报告。"
    system_prompt = f"""
你是首席数据分析师。你负责决定下一轮分析目标，或者在证据已经足够时结束分析循环。

输出规则：
1. 如果你认为之前的分析结果不足以生成可靠的报告，则你应该输出这一轮的分析目标，使用自然语言说明要验证什么、为什么要验证。
2. 如果已有分析轮次足以生成报告，第一行必须只输出 {READY_FOR_REPORT_FLAG}。
3. 不要输出 JSON。
4. 不要写 SQL，不要替证据规划师选择具体 SQL 字段。
""".strip()
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """决定继续请求数据证据，还是进入报告生成。

        输入:
            state: 当前图状态；通常包含用户问题、Skill、当前轮次、最大轮次和
                已沉淀的 `analysis_rounds`。

        输出:
            包含 `chief_message`、`director_action` 的状态更新；如果需要继续分析，
            还会包含 `analysis_goal`、递增后的 `analysis_round`，以及追加后的
            `agent_messages`。
        """
        current_round = int(state.get("analysis_round") or 0)
        max_rounds = int(state.get("max_analysis_rounds") or 3)
        analysis_rounds = list(state.get("analysis_rounds", []))

        if current_round >= max_rounds:
            message = f"{READY_FOR_REPORT_FLAG}\n已达到最大分析轮数 {max_rounds}，进入报告生成。"
            return {
                "chief_message": message,
                "director_action": "ready_for_report",
                "agent_messages": self.append_agent_message(state, current_round, message),
            }

        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        message = (raw_output or "").strip()
        action = self.detect_action(message, has_rounds=bool(analysis_rounds))
        if action == "ready_for_report" and not analysis_rounds:
            action = "need_evidence"

        analysis_goal = message
        if action == "need_evidence" and not analysis_goal:
            analysis_goal = f"围绕用户问题进行第 {current_round + 1} 轮数据证据分析"

        next_round = current_round + 1 if action == "need_evidence" else current_round
        output = {
            "chief_message": message,
            "director_action": action,
            "agent_messages": self.append_agent_message(state, next_round, message),
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
            要求模型输出下一轮分析目标，或固定报告标记的 prompt 字符串。
        """
        return f"""
用户问题：
{state["question"]}

已完成分析轮次 analysis_rounds：
{json_dumps(state.get("analysis_rounds", []))}

请输出下一轮分析目标，或输出 {READY_FOR_REPORT_FLAG}：
""".strip()

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造首席分析师的 system prompt，并加入 Skill 概览。

        输入:
            state: 当前图状态；包含已加载 Skill。

        输出:
            角色规则、输出格式和 Skill 概览组成的 system prompt。
        """
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

Skill 概览：
{skill.get("overview", "")}
""".strip()

    def detect_action(self, message: str, has_rounds: bool) -> str:
        """根据首席分析师文本判断流程是否进入报告生成。

        输入:
            message: 首席分析师原始输出文本。
            has_rounds: 当前是否已经至少完成一轮分析。

        输出:
            `ready_for_report` 或 `need_evidence`。
        """
        first_line = (message or "").strip().splitlines()[0].strip() if message else ""
        if first_line == READY_FOR_REPORT_FLAG and has_rounds:
            return "ready_for_report"
        if not message.strip() and has_rounds:
            return "ready_for_report"
        return "need_evidence"

    def append_agent_message(self, state: Dict[str, Any], round_number: int, message: str) -> list[Dict[str, Any]]:
        """把首席分析师输出追加到调试用对话历史中。

        输入:
            state: 当前图状态。
            round_number: 当前分析轮次。
            message: 首席分析师输出文本。

        输出:
            追加后的 `agent_messages` 列表。
        """
        messages = list(state.get("agent_messages", []))
        messages.append(
            {
                "round": round_number,
                "agent": self.name,
                "content": message,
            }
        )
        return messages

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
