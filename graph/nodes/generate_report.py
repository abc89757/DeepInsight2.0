from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode


class GenerateReportNode(AgentNode):
    name = "generate_report"
    title = "生成分析报告"
    description = "生成 Markdown 格式的数据分析报告。"
    system_prompt = "你擅长撰写结构化数据分析报告。"
    temperature = 0.3

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self.build_prompt(state)
        raw_report = self.call_llm(prompt, state)
        report = self.clean_report(raw_report)
        return self.write_report(state, report)

    def build_prompt(self, state: Dict[str, Any]) -> str:
        preview_text = json.dumps(
            state.get("result_preview", [])[:20],
            ensure_ascii=False,
            indent=2,
            default=str,
        )

        return f"""
你是一个数据洞察报告生成助手。请根据用户问题、SQL、数据分析结论、查询结果预览、场景 Skill 和报告模板，生成一份 Markdown 格式的数据分析报告。

要求：
1. 使用 Markdown；
2. 报告结构清晰，适合展示到前端；
3. 不要编造数据中没有的事实；
4. 如果只能初步判断，要使用谨慎表达；
5. 报告不需要特别长，当前是 MVP 版本，以清晰完整为主；
6. 使用中文输出。

用户问题：
{state["question"]}

执行 SQL：
{state["sql"]}

数据分析结论：
{state["analysis_result"]}

查询结果预览：
{preview_text}

场景 Skill：
{state["skill_content"]}

报告模板：
{state["report_template"]}

请生成 Markdown 报告：
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

    def clean_report(self, report: str) -> str:
        text = report.strip()
        if text.startswith("```markdown"):
            text = text.removeprefix("```markdown").strip()
        elif text.startswith("```"):
            text = text.removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    def write_report(self, state: Dict[str, Any], report: str) -> Dict[str, str]:
        output_path = Path(state["output_dir"])
        output_path.mkdir(parents=True, exist_ok=True)

        report_path = output_path / "report.md"
        report_path.write_text(report, encoding="utf-8")

        metadata_path = output_path / "metadata.json"
        metadata_path.write_text(
            json.dumps(
                {
                    "question": state["question"],
                    "sql": state["sql"],
                    "analysis_result": state["analysis_result"],
                    "report_path": str(report_path),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "report": report,
            "report_path": str(report_path),
            "metadata_path": str(metadata_path),
        }

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        report = output.get("report") or ""
        return f"分析报告生成完成，报告长度 {len(report)}。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "report_path": output.get("report_path"),
            "metadata_path": output.get("metadata_path"),
        }
