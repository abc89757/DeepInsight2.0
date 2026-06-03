"""图表生成节点。

这个文件定义 ChartGeneratorNode，用来在所有分析轮次结束后，根据分析结果、数据文件和 Skill 图表规则生成图表计划，
并从工具调用日志中整理最终可供报告引用的图表产物。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps
from services.task_tool_registry import get_task_tools
from services.tool_call_store import load_tool_calls


class ChartGeneratorNode(AgentNode):
    """负责根据最终分析结果生成报告图表的 AgentNode。"""

    name = "chart_generator"
    title = "图表策划师"
    description = "根据分析结果和数据文件生成报告所需图表。"
    system_prompt = """
你是数据分析报告的图表策划师。你的任务是在最终报告生成前，根据用户问题、分析轮次、数据文件和图表规则，选择最适合报告引用的图表。
你只需要生成有助于说明结论的图表，不要为了画图而画图。
每张图必须服务一个清晰的信息点，并且要有标题和 1-3 句话 caption。
如果当前还没有可用画图工具，或者数据不适合画图，请直接说明原因，不要编造图表路径。
默认最多规划或生成 3 张图。
""".strip()
    temperature = 0.2
    use_stream = True

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成图表计划，并整理工具实际生成的图表产物。

        输入:
            state: 当前图状态；包含用户问题、analysis_rounds、query_artifacts 和 Skill 图表规则。
        输出:
            包含 `chart_message`、`chart_artifacts` 和 `chart_issues` 的状态更新。
        """
        self.tools = get_task_tools(
            str(state.get("task_id")) if state.get("task_id") else None,
            "chart_generator",
        )
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output, label="raw_charts")
        chart_message = (raw_output or "").strip()
        chart_artifacts = self.collect_chart_artifacts(state)

        return {
            "chart_message": chart_message,
            "chart_artifacts": chart_artifacts
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造图表生成 prompt。

        输入:
            state: 当前图状态；包含用户问题、分析结果、数据文件和图表规则。
        输出:
            要求模型规划或调用工具生成图表的 prompt 字符串。
        """
        csv_files = self.scan_output_csv_files(state)
        csv_files_text = f"任务输出目录下发现的 CSV 文件：\n{json_dumps(csv_files)}\n\n"
        return f"""
{csv_files_text}
用户问题：
{state.get("question", "")}

分析轮次：
{json_dumps(state.get("analysis_rounds", []))}

可用数据文件：
{json_dumps(state.get("query_artifacts", []))}

图表输出目录：
{str(Path(state.get("output_dir", "outputs")) / "charts")}

可用画图工具：
{json_dumps([getattr(tool, "name", str(tool)) for tool in self.tools])}

要求：
1. 根据分析结果和可用数据文件判断是否需要图表。
2. 最多生成 3 张图。
3. 如果可用画图工具不为空，并且数据适合画图，必须调用工具生成真实图片。
4. 优先选择饼图、柱状图、折线图。
5. 每张图都要有标题、图表类型、数据来源、caption 和数据限制说明。
6. 如果工具不可用或数据不适合画图，说明原因即可。
""".strip()

    def scan_output_csv_files(self, state: Dict[str, Any]) -> list[Dict[str, Any]]:
        """扫描当前任务输出目录下的 CSV 文件并生成数据概览。

        输入:
            state: 当前图状态；包含 output_dir。
        输出:
            每个 CSV 的路径、字段、行数和随机预览行。
        """
        output_dir = Path(state.get("output_dir") or "")
        if not output_dir.exists():
            return []

        files: list[Dict[str, Any]] = []
        for csv_path in sorted(output_dir.rglob("*.csv")):
            try:
                df = pd.read_csv(csv_path)
                preview_count = min(5, len(df))
                preview = df.sample(n=preview_count, random_state=42).to_dict(orient="records") if preview_count else []
                files.append(
                    {
                        "path": str(csv_path),
                        "row_count": int(len(df)),
                        "columns": list(df.columns),
                        "preview_rows": preview,
                    }
                )
            except Exception as exc:
                files.append({"path": str(csv_path), "error": str(exc)})
        return files

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造图表生成节点的 system prompt，并加入 Skill 图表规则。

        输入:
            state: 当前图状态；包含已加载 Skill。
        输出:
            角色规则和 Skill 图表规则组成的 system prompt。
        """
        skill = state.get("skill") or {}
        charts_rule = skill.get("charts", "") or ""
        return f"""
{self.system_prompt}

Skill 图表规则：
{charts_rule}
""".strip()

    def collect_chart_artifacts(self, state: Dict[str, Any]) -> list[Dict[str, Any]]:
        """从工具调用日志中提取成功生成的图表产物。

        输入:
            state: 当前图状态；包含 task_id。
        输出:
            可供报告引用的图表产物列表。
        """
        task_id = str(state.get("task_id")) if state.get("task_id") else None
        artifacts: list[Dict[str, Any]] = []
        for record in load_tool_calls(task_id, node_name=self.name):
            result = record.get("result")
            if not isinstance(result, dict) or not result.get("success"):
                continue
            file_path = result.get("file_path") or result.get("chart_path") or result.get("output_path")
            if not file_path:
                continue
            artifacts.append(
                {
                    "title": result.get("title") or result.get("chart_title") or "未命名图表",
                    "chart_type": result.get("chart_type") or result.get("type"),
                    "file_path": file_path,
                    "data_source": result.get("data_source") or result.get("source_file_path"),
                    "description": result.get("description") or result.get("summary") or "",
                    "caption": result.get("caption") or result.get("description") or "",
                    "columns_used": result.get("columns_used") or [],
                    "related_round": result.get("related_round"),
                    "status": "success",
                }
            )
        return artifacts

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于前端步骤卡片展示的图表节点摘要。

        输入:
            output: `run` 返回的状态更新。
        输出:
            优先以 caption + Markdown 图片语法展示图表；无图时返回节点说明。
        """
        artifacts = output.get("chart_artifacts") or []
        if artifacts:
            chunks = []
            for artifact in artifacts:
                title = artifact.get("title") or "图表"
                caption = artifact.get("caption") or artifact.get("description") or ""
                file_path = artifact.get("file_path") or ""
                chunks.append(f"{caption}\n\n![{title}]({file_path})".strip())
            return "\n\n".join(chunks)
        return output.get("chart_message") or "图表节点已完成，未生成图表。"
