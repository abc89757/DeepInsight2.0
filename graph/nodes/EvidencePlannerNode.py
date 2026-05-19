"""证据规划师节点。

这个文件定义 EvidencePlannerNode，用来把首席分析师给出的分析目标转成可执行的数据证据规划。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps, parse_json_object


class EvidencePlannerNode(AgentNode):
    """负责把分析目标转成查询规格和数据处理要求的 AgentNode。"""

    name = "evidence_planner"
    title = "证据规划师"
    description = "根据分析目标规划需要的数据证据、指标、特征和查询规格。"
    system_prompt = "你是证据规划师。你只输出 JSON，不输出解释。"
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """为当前分析轮次生成证据规划。

        输入:
            state: 当前图状态；需要包含 `question`，通常还包含 `analysis_goal`、
                `schema_info` 和已加载的 `skill`。

        输出:
            包含 `current_query_id`、`current_evidence_plan` 和重置后
            `sql_attempts` 的状态更新。
        """
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        plan = parse_json_object(raw_output)
        query_id = f"q{int(state.get('analysis_round') or 1):03d}"
        if not plan:
            plan = {
                "purpose": state.get("analysis_goal") or state["question"],
                "evidence_type": "unknown",
                "evidence_items": [],
                "sql_guidance": "优先使用只读 SELECT；返回能够支撑分析目标的字段和必要聚合。",
                "processing_guidance": "根据查询结果生成摘要、证据项处理结果和数据问题。",
            }
        plan["query_id"] = query_id
        return {
            "current_query_id": query_id,
            "current_evidence_plan": plan,
            "sql_attempts": 0,
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造证据规划 prompt。

        输入:
            state: 当前图状态；包含分析目标、数据库 Schema、Skill 内容和已完成的分析轮次。

        输出:
            要求模型返回 JSON 证据规划的 prompt 字符串。
        """
        skill = state.get("skill") or {}
        return f"""
请根据本轮分析目标、数据库 Schema 和 Skill，规划需要的数据证据。
你不直接写 SQL，但要给 SQL 工程师足够明确的查询指导，也要给数据处理师明确的处理要求。

用户问题：
{state["question"]}

本轮分析目标：
{state.get("analysis_goal", "")}

数据库 Schema：
{state.get("schema_info", "")}

Skill 指标/证据规则：
{skill.get("metrics", "")}

Skill 计算/取数规则：
{skill.get("calculations", "")}

已完成分析轮次：
{json_dumps(state.get("analysis_rounds", []))}

要求：
1. 只输出 JSON，不要输出 Markdown 或解释。
2. JSON 字符串内部如果需要引用字段值、标签或原文，请使用单引号或中文引号，不要使用英文双引号；如果必须使用英文双引号，必须写成转义形式 `\"`。

只输出 JSON：
{{
  "purpose": "本轮取数目的",
  "evidence_type": "aggregate/detail/feature/sample",
  "evidence_items": ["计划使用的指标、特征或证据项"],
  "dimensions": ["需要分组或对比的维度"],
  "filters": ["过滤条件或数据口径"],
  "time_range": "时间范围，如果无法判断则为空",
  "sql_guidance": "给 SQL 工程师的具体查询和聚合指导",
  "expected_result_shape": ["期望返回的列或数据形状"],
  "processing_guidance": "给数据处理师的后续处理要求"
}}
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用配置好的 LLM 完成证据规划。

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
        """生成用于任务步骤日志的证据规划摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        plan = output.get("current_evidence_plan") or {}
        return f"证据规划完成：{plan.get('purpose', '')}"
