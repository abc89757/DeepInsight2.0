"""洞察分析师节点。

这个文件定义 InsightAnalystNode，用来把本轮目标、证据规划和数据处理结果沉淀成一轮分析包。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps


class InsightAnalystNode(AgentNode):
    """负责把本轮数据证据转成自然语言分析结果，并追加到 analysis_rounds 的 AgentNode。"""

    name = "insight_analyst"
    title = "洞察分析师"
    description = "把本轮处理结果转化为分析结果，并归档本轮分析包。"
    system_prompt = """
你是数据洞察分析师。你负责基于已有数据证据给出本轮分析结果和限制说明。

要求：
1. 只基于当前数据证据，不要编造。
2. 不要重复罗列原始 SQL 或文件路径。
3. 如果当前证据不能支持某些判断，要明确写在限制或问题里。
4. 需要说明本轮证据对用户问题有什么推进，以及是否建议首席分析师下一轮继续补证据。

请用自然语言输出，建议使用这些小标题：
【分析结果】本轮证据共同说明了什么。
【数据缺陷】如果数据层问题会影响结论，请复述或补充；如果没有明显问题，写“暂未发现明显数据层缺陷”。
【分析限制】说明不能做哪些过度推断，例如不能做因果判断、缺少外部变量、证据不足。
【下一步建议】如果继续分析，建议首席分析师下一轮关注什么；如果已经足够生成报告，也可以说明。
""".strip()
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成本轮分析结果包，并追加到 `analysis_rounds`。

        输入:
            state: 当前图状态；包含分析目标、证据规划、数据处理结果和已有分析轮次。

        输出:
            包含 `insight_message`、`current_analysis_round` 和追加后 `analysis_rounds` 的状态更新。
        """
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        insight_message = (raw_output or "").strip()
        if not insight_message:
            raise ValueError("洞察分析师没有返回有效内容。")

        analysis_issue = self.extract_analysis_issue(insight_message)
        data_issue = self.merge_issue_text(
            state.get("current_data_issue", ""),
            self.extract_data_issue(insight_message),
        )
        round_package = {
            "round": int(state.get("analysis_round") or 0),
            "analysis_goal": state.get("analysis_goal", ""),
            "evidence_plan": state.get("evidence_message", ""),
            "evidence_result": state.get("data_message", ""),
            "analysis_result": insight_message,
            "data_issue": data_issue,
            "analysis_issue": analysis_issue,
        }
        analysis_rounds = list(state.get("analysis_rounds", [])) + [round_package]

        return {
            "insight_message": insight_message,
            "current_insight": {"message": insight_message},
            "current_analysis_issue": analysis_issue,
            "current_analysis_round": round_package,
            "analysis_rounds": analysis_rounds,
            "analysis_result": insight_message,
            "agent_messages": self.append_agent_message(state, insight_message),
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造洞察分析 prompt。

        输入:
            state: 当前图状态；包含用户问题、分析目标、当前证据规划、数据处理结果
                和已完成的分析轮次。

        输出:
            要求模型以自然语言返回本轮分析结果和限制说明的 prompt 字符串。
        """
        return f"""
用户问题：
{state.get("question", "")}

本轮分析目标：
{state.get("analysis_goal", "")}

证据规划：
{state.get("evidence_message") or json_dumps(state.get("current_evidence_plan", {}))}

数据处理结果：
{state.get("data_message") or json_dumps(state.get("current_processed_data", {}))}

已完成分析轮次：
{json_dumps(state.get("analysis_rounds", []))}
""".strip()

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造洞察分析师的 system prompt，并加入 Skill 分析规则。

        输入:
            state: 当前图状态；包含已加载 Skill。

        输出:
            角色规则、输出格式和 Skill 内容组成的 system prompt。
        """
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

Skill 分析规则：
{skill.get("analysis", "")}
""".strip()

    def extract_data_issue(self, message: str) -> str:
        """从洞察分析师输出中提取“数据缺陷”段落。

        输入:
            message: 洞察分析师输出文本。

        输出:
            数据缺陷说明；如果没有找到专门段落，则返回空字符串。
        """
        return self.extract_marked_section(message, "【数据缺陷】", ["【分析限制】", "【下一步建议】"])

    def extract_analysis_issue(self, message: str) -> str:
        """从洞察分析师输出中提取“分析限制”段落。

        输入:
            message: 洞察分析师输出文本。

        输出:
            分析限制说明；如果没有找到专门段落，则返回空字符串。
        """
        return self.extract_marked_section(message, "【分析限制】", ["【下一步建议】"])

    def extract_marked_section(self, message: str, marker: str, next_markers: list[str]) -> str:
        """按中文小标题从自然语言输出中截取一段内容。

        输入:
            message: 完整输出文本。
            marker: 当前段落小标题。
            next_markers: 可能出现在后面的下一个小标题列表。

        输出:
            当前小标题下的文本内容；找不到时返回空字符串。
        """
        if marker not in message:
            return ""
        section = message.split(marker, 1)[1]
        for next_marker in next_markers:
            if next_marker in section:
                section = section.split(next_marker, 1)[0]
        return section.strip()

    def merge_issue_text(self, data_issue: Any, insight_data_issue: str) -> str:
        """合并数据处理师和洞察分析师给出的数据缺陷说明。

        输入:
            data_issue: 数据处理师提取出的数据缺陷，可能是字符串或旧结构列表。
            insight_data_issue: 洞察分析师补充的数据缺陷。

        输出:
            合并后的数据缺陷说明文本。
        """
        parts: list[str] = []
        if isinstance(data_issue, list):
            parts.extend(str(item).strip() for item in data_issue if str(item).strip())
        elif str(data_issue or "").strip():
            parts.append(str(data_issue).strip())
        if insight_data_issue.strip():
            parts.append(insight_data_issue.strip())
        return "\n\n".join(parts)

    def append_agent_message(self, state: Dict[str, Any], message: str) -> list[Dict[str, Any]]:
        """把洞察分析师输出追加到调试用对话历史中。

        输入:
            state: 当前图状态。
            message: 洞察分析师输出文本。

        输出:
            追加后的 `agent_messages` 列表。
        """
        messages = list(state.get("agent_messages", []))
        messages.append(
            {
                "round": int(state.get("analysis_round") or 0),
                "agent": self.name,
                "content": message,
            }
        )
        return messages

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的洞察分析摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        return output.get("insight_message", "") or "本轮洞察分析完成。"
