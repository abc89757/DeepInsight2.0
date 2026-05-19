"""洞察分析师节点。

这个文件定义 InsightAnalystNode，用来把处理后的数据证据沉淀成一轮分析包。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps, parse_json_object


class InsightAnalystNode(AgentNode):
    """负责把本轮证据转成分析结果，并追加到 analysis_rounds 的 AgentNode。"""

    name = "insight_analyst"
    title = "洞察分析师"
    description = "把本轮处理结果转化为一轮分析结果、证据项和问题说明。"
    system_prompt = "你是数据洞察分析师。你只输出 JSON，不输出解释。"
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成本轮分析结果包，并追加到 `analysis_rounds`。

        输入:
            state: 当前图状态；包含分析目标、证据规划、处理后的数据证据项和已有分析轮次。

        输出:
            包含 `current_insight`、`current_analysis_issue`、`current_analysis_round`
            和追加后 `analysis_rounds` 的状态更新。
        """
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        insight = parse_json_object(raw_output)
        if not insight:
            raise ValueError("洞察分析师没有返回有效 JSON。")

        analysis_issue = insight.get("analysis_issue")
        if not isinstance(analysis_issue, list):
            analysis_issue = []

        processed_data = state.get("current_processed_data", {})
        evidence_items = processed_data.get("evidence_items", [])
        if not isinstance(evidence_items, list):
            evidence_items = []

        round_package = {
            "round": int(state.get("analysis_round") or 0),
            "analysis_goal": state.get("analysis_goal", ""),
            "evidence_items": evidence_items,
            "analysis_result": insight.get("analysis_result", ""),
            "issues": {
                "data_issue": state.get("current_data_issue", []),
                "analysis_issue": analysis_issue,
            },
        }
        analysis_rounds = list(state.get("analysis_rounds", [])) + [round_package]

        return {
            "current_insight": insight,
            "current_analysis_issue": analysis_issue,
            "current_analysis_round": round_package,
            "analysis_rounds": analysis_rounds,
            "analysis_result": insight.get("analysis_result", ""),
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造洞察分析 prompt。

        输入:
            state: 当前图状态；包含用户问题、分析目标、当前证据规划、处理后数据
                和已完成的分析轮次。

        输出:
            要求模型以 JSON 返回本轮分析结果和分析层问题的 prompt 字符串。
        """
        skill = state.get("skill") or {}
        return f"""
请基于本轮分析目标、证据规划和数据处理结果，生成本轮分析结论。
要求：
1. 只基于当前数据证据，不要编造。
2. 不要重复罗列原始 SQL 或文件路径。
3. 如果当前证据不能支持某些判断，要写入 analysis_issue。
4. 不要输出 confidence 字段。

用户问题：
{state["question"]}

本轮分析目标：
{state.get("analysis_goal", "")}

证据规划：
{json_dumps(state.get("current_evidence_plan", {}))}

数据处理结果：
{json_dumps(state.get("current_processed_data", {}))}

已完成分析轮次：
{json_dumps(state.get("analysis_rounds", []))}

Skill 分析规则：
{skill.get("analysis", "")}

要求：
1. 只输出 JSON，不要输出 Markdown 或解释。
2. JSON 字符串内部如果需要引用字段值、标签或原文，请使用单引号或中文引号，不要使用英文双引号；如果必须使用英文双引号，必须写成转义形式 `\"`。

只输出 JSON：
{{
  "analysis_result": "本轮分析结论，说明这些证据共同回答了什么",
  "analysis_issue": [
    "分析层限制，例如不能做因果判断、缺少外部变量、证据不足"
  ],
  "recommended_next_focus": "如果继续分析，建议下一步关注什么"
}}
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用配置好的 LLM 完成洞察分析。

        输入:
            prompt: `build_prompt` 生成的 prompt。
            state: 当前图状态；此处主要用于保持 AgentNode 接口一致。

        输出:
            预期包含 JSON 对象的模型原始文本。
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
        """生成用于任务步骤日志的洞察分析摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        insight = output.get("current_insight") or {}
        return insight.get("analysis_result") or "本轮洞察分析完成。"
