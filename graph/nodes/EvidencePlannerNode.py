"""证据规划师节点。

这个文件定义 EvidencePlannerNode，用来把首席分析师给出的分析目标转成可执行的数据证据规划。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps


class EvidencePlannerNode(AgentNode):
    """负责把分析目标转成查询规格和数据处理要求的 AgentNode。"""

    name = "evidence_planner"
    title = "证据规划师"
    description = "根据分析目标规划需要的数据证据、指标、特征和查询规格。"
    system_prompt = """
你是证据规划师。你负责把分析目标转成可执行的数据证据方案。
你不直接写 SQL，但要给 SQL 工程师足够明确的查询指导，也要给数据处理师明确的处理要求。

请用自然语言输出证据方案，建议包含这些内容：
【证据目标】这轮证据要回答什么。
【证据/特征选择】要观察哪些指标、特征、明细记录或规则命中结果；不要局限于传统指标。
【数据口径】需要哪些过滤条件、分组维度、时间范围或样本范围。
【SQL指导】告诉 SQL 工程师应该如何取数或聚合，但不要直接写完整 SQL。
【数据处理要求】告诉数据处理师拿到结果后要说明哪些具体数据情况、指标结果和潜在数据缺陷。
""".strip()
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """为当前分析轮次生成证据规划。

        输入:
            state: 当前图状态；需要包含 `question`，通常还包含 `analysis_goal`、
                `schema_info` 和已加载的 `skill`。

        输出:
            包含 `evidence_message`、`current_query_id`、`current_evidence_plan` 和重置后
            `sql_attempts` 的状态更新。
        """
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        evidence_message = (raw_output or "").strip()
        query_id = f"q{int(state.get('analysis_round') or 1):03d}"
        if not evidence_message:
            evidence_message = (
                "围绕本轮分析目标规划数据证据：优先使用只读 SELECT，返回能够支撑分析目标的字段、"
                "必要聚合结果、关键数据口径，并让数据处理师说明具体数据情况和数据缺陷。"
            )
        plan = {
            "query_id": query_id,
            "message": evidence_message,
        }
        return {
            "evidence_message": evidence_message,
            "current_query_id": query_id,
            "current_evidence_plan": plan,
            "sql_attempts": 0,
            "agent_messages": self.append_agent_message(state, evidence_message),
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造证据规划 prompt。

        输入:
            state: 当前图状态；包含分析目标、数据库 Schema、Skill 内容和已完成的分析轮次。

        输出:
            要求模型返回自然语言证据规划的 prompt 字符串。
        """
        return f"""
用户问题：
{state["question"]}

本轮分析目标：
{state.get("analysis_goal", "")}

数据库 Schema：
{state.get("schema_info", "")}

已完成分析轮次：
{json_dumps(state.get("analysis_rounds", []))}
""".strip()

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造证据规划师的 system prompt，并加入 Skill 证据/取数规则。

        输入:
            state: 当前图状态；包含已加载 Skill。

        输出:
            角色规则、输出格式和 Skill 内容组成的 system prompt。
        """
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

Skill 指标/证据规则：
{skill.get("metrics", "")}

Skill 计算/取数规则：
{skill.get("calculations", "")}
""".strip()

    def append_agent_message(self, state: Dict[str, Any], message: str) -> list[Dict[str, Any]]:
        """把证据规划师输出追加到调试用对话历史中。

        输入:
            state: 当前图状态。
            message: 证据规划师输出文本。

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
        """生成用于任务步骤日志的证据规划摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        return output.get("evidence_message", "") or "证据规划完成。"
