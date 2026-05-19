"""报告撰写人节点。

这个文件定义 ReportWriterNode，用来根据 analysis_rounds 和报告模板生成 Markdown 报告。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps


class ReportWriterNode(AgentNode):
    """负责生成并保存最终 Markdown 分析报告的 AgentNode。"""

    name = "report_writer"
    title = "报告撰写人"
    description = "根据所有分析轮次生成结构化 Markdown 报告。"
    system_prompt = "你是结构化数据分析报告撰写人。"
    temperature = 0.3

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成最终报告并写入本地文件。

        输入:
            state: 当前图状态；包含用户问题、`analysis_rounds`、输出目录和可选报告模板。

        输出:
            包含报告正文和报告元数据路径的状态更新。
        """
        raw_report = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_report, label="raw_report")
        report = self.clean_report(raw_report)
        return self.write_report(state, report)

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造最终报告撰写 prompt。

        输入:
            state: 当前图状态；包含用户问题、所有分析轮次和 Skill 报告模板。

        输出:
            要求模型输出 Markdown 报告的 prompt 字符串。
        """
        skill = state.get("skill") or {}
        return f"""
请根据用户问题和 analysis_rounds 生成一份 Markdown 结构化数据分析报告。
analysis_rounds 中每一轮都包含分析目标、证据项处理结果、分析结论和问题说明。
不要引用 SQL、文件路径或 artifact，除非用户明确要求技术细节。

要求：
1. 使用中文。
2. 优先呈现已经有证据支持的结论。
3. 每轮 issues 中的 data_issue 和 analysis_issue 要在报告中以“数据与分析限制”说明。
4. 不要编造数据库中没有的信息。
5. 报告不需要特别长，但要结构清楚。

用户问题：
{state["question"]}

分析轮次：
{json_dumps(state.get("analysis_rounds", []))}

报告模板：
{skill.get("report_template") or state.get("report_template", "")}

请输出 Markdown 报告：
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        """调用配置好的 LLM 完成报告撰写。

        输入:
            prompt: `build_prompt` 生成的 prompt。
            state: 当前图状态；此处主要用于保持 AgentNode 接口一致。

        输出:
            模型返回的 Markdown 原始文本。
        """
        return self.llm_client.complete(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=self.temperature,
            tools=self.tools,
            stream=self.stream,
            timeout=self.timeout,
        )

    def clean_report(self, report: str) -> str:
        """去掉模型可能包裹在报告外层的 Markdown 代码块。

        输入:
            report: 模型原始输出；可能被 Markdown 代码块包裹。

        输出:
            清理后的 Markdown 报告正文。
        """
        text = (report or "").strip()
        if text.startswith("```markdown"):
            text = text.removeprefix("```markdown").strip()
        elif text.startswith("```"):
            text = text.removeprefix("```").strip()
        if text.endswith("```"):
            text = text[:-3].strip()
        return text

    def write_report(self, state: Dict[str, Any], report: str) -> Dict[str, str]:
        """把报告和元数据写入当前任务输出目录。

        输入:
            state: 当前图状态；需要包含 `output_dir`、用户问题、Skill 和 `analysis_rounds`。
            report: 清理后的 Markdown 报告正文。

        输出:
            包含 `report`、`report_path` 和 `metadata_path` 的状态更新。
        """
        output_path = Path(state["output_dir"])
        output_path.mkdir(parents=True, exist_ok=True)

        report_path = output_path / "report.md"
        report_path.write_text(report, encoding="utf-8")

        metadata_path = output_path / "metadata.json"
        metadata_path.write_text(
            json_dumps(
                {
                    "question": state["question"],
                    "selected_skill_name": state.get("selected_skill_name"),
                    "analysis_rounds": state.get("analysis_rounds", []),
                    "report_path": str(report_path),
                }
            ),
            encoding="utf-8",
        )

        return {
            "report": report,
            "report_path": str(report_path),
            "metadata_path": str(metadata_path),
        }

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的报告生成摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        report = output.get("report") or ""
        return f"报告生成完成，长度 {len(report)}。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """挑选适合持久化到任务步骤里的报告元数据。

        输入:
            output: `run` 返回的状态更新。

        输出:
            只包含报告文件路径的简短 dict。
        """
        return {
            "report_path": output.get("report_path"),
            "metadata_path": output.get("metadata_path"),
        }
