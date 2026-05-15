from __future__ import annotations

import json
from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode


class AnalyzeDataNode(AgentNode):
    name = "analyze_data"
    title = "分析查询结果"
    description = "基于查询结果预览提炼数据发现。"
    system_prompt = "你擅长根据结构化查询结果提炼数据洞察。"
    temperature = 0.2

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self.build_prompt(state)
        analysis_result = self.call_llm(prompt, state).strip()
        return {"analysis_result": analysis_result}

    def build_prompt(self, state: Dict[str, Any]) -> str:
        preview_text = json.dumps(
            state.get("result_preview", []),
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        return f"""
你是一个数据分析助手。请根据用户问题、执行 SQL、查询结果预览和场景 Skill，给出简洁但有用的数据分析结论。

要求：
1. 不要编造数据库中没有的信息；
2. 如果结果不足以支持因果判断，要明确说明只能初步判断；
3. 重点输出：数据概览、关键发现、可能异常、后续报告要点；
4. 不要写成完整正式报告，后面还有报告生成模块；
5. 使用中文输出。

用户问题：
{state["question"]}

执行 SQL：
{state["sql"]}

结果字段：
{state.get("result_columns", [])}

结果行数：
{state.get("result_row_count", 0)}

结果预览：
{preview_text}

场景 Skill：
{state["skill_content"]}

请输出数据分析结论：
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
        analysis_result = output.get("analysis_result") or ""
        return f"数据分析完成，分析结论长度 {len(analysis_result)}。"
