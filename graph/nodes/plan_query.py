from __future__ import annotations

from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode


class PlanQueryNode(AgentNode):
    name = "plan_query"
    title = "规划查询任务"
    description = "根据问题、Schema 和业务规则规划需要查询的数据。"
    system_prompt = "你擅长把自然语言数据分析需求转化为清晰的查询规划。"
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self.build_prompt(state)
        query_plan = self.call_llm(prompt, state).strip()
        return {"query_plan": query_plan}

    def build_prompt(self, state: Dict[str, Any]) -> str:
        return f"""
你是一个数据分析任务规划助手。请根据用户问题、数据库表结构和场景 Skill，规划本次查询任务。

要求：
1. 只规划需要查询什么数据，不要生成 SQL；
2. 指出可能需要使用的表和字段；
3. 指出需要统计的指标或分组维度；
4. 输出简洁，不要写成长篇报告。

用户问题：
{state["question"]}

报告深度：
{state.get("report_depth", "standard")}

数据库 Schema：
{state["schema_info"]}

场景 Skill：
{state["skill_content"]}

请输出查询规划：
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        return self.llm_client.complete(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=self.temperature,
            tools=self.tools,
            stream=self.stream,
            timeout=self.timeout,
        )

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        query_plan = output.get("query_plan") or ""
        return f"查询规划生成完成，规划文本长度 {len(query_plan)}。"
