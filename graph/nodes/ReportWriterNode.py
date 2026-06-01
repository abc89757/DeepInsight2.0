"""报告撰写人节点。

这个文件定义 ReportWriterNode，用来根据 analysis_rounds 和报告模板生成 Markdown 报告。
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import pandas as pd
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps


class ReadDataRowsInput(BaseModel):
    """报告生成器读取 CSV 数据行的工具参数。"""

    file_path: str = Field(description="CSV 文件路径，必须传入。")
    filter_column: Optional[str] = Field(default=None, description="可选。需要筛选的字段名。")
    filter_value: Optional[str] = Field(default=None, description="可选。筛选字段需要等于的内容，会按字符串形式比较。")
    sort_column: Optional[str] = Field(default=None, description="可选。需要排序的字段名。")
    sort_direction: Literal["asc", "desc"] = Field(default="desc", description="排序方向：asc 升序，desc 降序。")
    start_index: int = Field(default=1, ge=1, description="1-based 起始下标。")
    limit: int = Field(default=50, ge=1, le=50, description="最多返回多少行；上限固定为 50。")


class ReportWriterNode(AgentNode):
    """负责生成并保存最终 Markdown 分析报告的 AgentNode。"""

    name = "report_writer"
    title = "报告撰写人"
    description = "根据所有分析轮次生成结构化 Markdown 报告。"
    system_prompt = """
你是结构化数据分析报告撰写人。
请根据用户问题和 analysis_rounds 生成一份 Markdown 结构化数据分析报告。
analysis_rounds 中每一轮都包含分析目标、证据方案、具体数据情况/证据结果、分析结果和数据缺陷。
不要引用 SQL、文件路径或 artifact，除非用户明确要求技术细节。

要求：
1. 使用中文。
2. 优先呈现已经有证据支持的结论。
3. 每轮 data_issue 和 analysis_issue 要在报告中以“数据与分析限制”说明。
4. 不要编造数据库中没有的信息。
5. 报告不需要特别长，但要结构清楚。
""".strip()
    temperature = 0.3
    use_stream = True

    def __init__(self) -> None:
        """初始化报告生成器，并注册通用数据读取工具。

        输入:
            无。
        输出:
            无返回值；实例会持有一个只给报告生成器使用的内置数据读取工具。
        """
        super().__init__()
        self.tools = [
            StructuredTool.from_function(
                func=self.read_data_rows,
                name="read_data_rows",
                description=(
                    "读取 CSV 文件中的少量数据行，可筛选、排序和分页。"
                    "当报告需要用 Markdown 表格展示真实数据样例或排名明细时调用。"
                ),
                args_schema=ReadDataRowsInput,
            )
        ]

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成最终报告并写入本地文件。

        输入:
            state: 当前图状态；包含用户问题、`analysis_rounds`、输出目录和可选报告模板。

        输出:
            包含报告正文和报告元数据路径的状态更新。
        """
        prompt = f"{self.build_prompt(state)}\n\n{self.get_report_data_files_text(state)}"
        prompt = f"{prompt}\n\n{self.get_chart_artifacts_text(state)}"
        raw_report = self.call_llm(prompt, state)
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
        return f"""
用户问题：
{state["question"]}

分析轮次：
{json_dumps(state.get("analysis_rounds", []))}

请输出 Markdown 报告：
""".strip()

    def get_report_data_files_text(self, state: Dict[str, Any]) -> str:
        """生成报告生成器可读取数据文件的说明文本。

        输入:
            state: 当前图状态。
        输出:
            包含 query_artifacts 的 JSON 文本片段。
        """
        return (
            "可读取的数据文件：\n"
            f"{json_dumps(state.get('query_artifacts', []))}\n\n"
            "如果报告中需要加入数据表格，可以调用 `read_data_rows` 读取已有 CSV 的少量行，"
            "然后用 Markdown 表格写入报告。表格只能引用工具返回的真实数据，不要编造表格内容。"
        )

    def get_chart_artifacts_text(self, state: Dict[str, Any]) -> str:
        """生成报告可引用图表的说明文本。

        输入:
            state: 当前图状态；包含 chart_artifacts 和 chart_issues。
        输出:
            给报告生成器使用的图表说明文本。
        """
        return (
            "可引用的图表产物：\n"
            f"{json_dumps(state.get('chart_artifacts', []))}\n\n"
            "图表生成问题：\n"
            f"{json_dumps(state.get('chart_issues', []))}\n\n"
            "如果存在可引用的图表文件，则报告必须在相关结论附近用 Markdown 图片语法引用，"
            "并在图下写 caption。不要引用不存在的图表。"
        )

    def build_system_prompt(self, state: Dict[str, Any]) -> str:
        """构造报告撰写人的 system prompt，并加入报告模板。

        输入:
            state: 当前图状态；包含已加载 Skill 和可选报告模板。

        输出:
            角色规则、报告要求和模板组成的 system prompt。
        """
        skill = state.get("skill") or {}
        return f"""
{self.system_prompt}

报告模板：
{skill.get("report_template") or state.get("report_template", "")}
""".strip()

    def read_data_rows(
        self,
        file_path: str,
        filter_column: Optional[str] = None,
        filter_value: Optional[str] = None,
        sort_column: Optional[str] = None,
        sort_direction: Literal["asc", "desc"] = "desc",
        start_index: int = 1,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """读取 CSV 数据行，支持筛选、排序和分页。

        输入:
            file_path: CSV 文件路径。
            filter_column: 可选筛选字段名。
            filter_value: 可选筛选字段值；会按字符串等值比较。
            sort_column: 可选排序字段名。
            sort_direction: 排序方向，`asc` 或 `desc`。
            start_index: 1-based 起始下标。
            limit: 返回行数，上限 50。
        输出:
            包含字段名、二维数组行数据、行数统计和错误信息的字典。
        """
        try:
            path = Path(file_path)
            if not path.exists():
                raise FileNotFoundError(f"文件不存在：{file_path}")

            df = pd.read_csv(path)
            original_row_count = len(df)

            if filter_column:
                self.require_column(df, filter_column)
                if filter_value is None:
                    raise ValueError("传入 filter_column 时必须同时传入 filter_value。")
                df = df[df[filter_column].astype(str) == str(filter_value)]

            if sort_column:
                self.require_column(df, sort_column)
                numeric_values = pd.to_numeric(df[sort_column], errors="coerce")
                if numeric_values.notna().any():
                    df = df.assign(_sort_key=numeric_values).sort_values(
                        "_sort_key",
                        ascending=sort_direction == "asc",
                        na_position="last",
                    )
                    df = df.drop(columns=["_sort_key"])
                    sort_mode = "numeric"
                else:
                    df = df.sort_values(sort_column, ascending=sort_direction == "asc", na_position="last")
                    sort_mode = "text"
            else:
                sort_mode = None

            total_rows = len(df)
            clean_start = max(1, int(start_index or 1))
            clean_limit = max(1, min(int(limit or 50), 50))
            page = df.iloc[clean_start - 1 : clean_start - 1 + clean_limit]

            return {
                "success": True,
                "file_path": file_path,
                "original_row_count": original_row_count,
                "matched_row_count": total_rows,
                "start_index": clean_start,
                "limit": clean_limit,
                "returned_row_count": len(page),
                "has_more": clean_start - 1 + clean_limit < total_rows,
                "filter_column": filter_column,
                "filter_value": filter_value,
                "sort_column": sort_column,
                "sort_direction": sort_direction if sort_column else None,
                "sort_mode": sort_mode,
                "columns": list(df.columns),
                "rows": self.rows_as_lists(page),
            }
        except Exception as exc:
            return {
                "success": False,
                "error_type": exc.__class__.__name__,
                "error_message": str(exc),
            }

    def require_column(self, df: pd.DataFrame, column_name: str) -> None:
        """检查 DataFrame 中是否存在指定字段。

        输入:
            df: 待检查 DataFrame。
            column_name: 字段名。
        输出:
            无返回值；字段不存在时抛出 ValueError。
        """
        if column_name not in df.columns:
            raise ValueError(f"字段不存在：{column_name}；可用字段：{list(df.columns)}")

    def rows_as_lists(self, df: pd.DataFrame) -> list[list[Any]]:
        """把 DataFrame 转为列表套列表。

        输入:
            df: 待转换 DataFrame。
        输出:
            每行一个列表的二维数组。
        """
        return [[self.serialize_value(value) for value in row] for row in df.to_numpy().tolist()]

    def serialize_value(self, value: Any) -> Any:
        """把 pandas/numpy 值转换成 JSON 友好的值。

        输入:
            value: 原始单元格值。
        输出:
            可 JSON 序列化的值。
        """
        if pd.isna(value):
            return None
        if hasattr(value, "item"):
            value = value.item()
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return None
        return value

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
