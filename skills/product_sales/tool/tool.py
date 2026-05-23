"""product_sales 场景的数据处理 MCP 工具。

这个文件提供给 DataProcessorNode 使用，主要支持 CSV 数据的抽样筛选、字段格式占比、
字段内容占比，以及新增两列相加计算列。所有工具都会捕获异常并返回错误信息，避免中断 Graph。
"""

from __future__ import annotations

import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import Field


mcp = FastMCP("product_sales_data_tools")
LOG_DIR = Path("tool_call_logs")
MAX_RETURN_ROWS = 50
MAX_RATIO_ITEMS = 50


def _log_tool_call(tool_name: str, detail: str) -> None:
    """记录工具调用日志。

    输入:
        tool_name: 被调用的工具名称。
        detail: 调用摘要。
    输出:
        无返回值；日志会写入本地文件并打印到 stderr。
    """
    message = f"{datetime.now().isoformat(timespec='seconds')} [{tool_name}] {detail}"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "product_sales_tool_calls.log").open("a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")
    print(f"[product_sales data tool] {message}", file=sys.stderr, flush=True)


def _error(tool_name: str, exc: Exception) -> dict[str, Any]:
    """把异常转换为工具返回值。

    输入:
        tool_name: 当前工具名称。
        exc: 捕获到的异常对象。
    输出:
        包含 success=false 和错误信息的字典。
    """
    _log_tool_call(tool_name, f"error={exc}")
    return {
        "success": False,
        "error_type": exc.__class__.__name__,
        "error_message": str(exc),
    }


def _read_csv(file_path: str) -> pd.DataFrame:
    """读取 CSV 文件。

    输入:
        file_path: CSV 文件路径。
    输出:
        pandas DataFrame。
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在：{file_path}")
    return pd.read_csv(path)


def _require_column(df: pd.DataFrame, column_name: str) -> None:
    """检查字段是否存在。

    输入:
        df: 待检查 DataFrame。
        column_name: 字段名。
    输出:
        无返回值；字段不存在时抛出 ValueError。
    """
    if column_name not in df.columns:
        raise ValueError(f"字段不存在：{column_name}；可用字段：{list(df.columns)}")


def _clean_limit(limit: int) -> int:
    """把返回行数限制在 1 到 MAX_RETURN_ROWS 之间。

    输入:
        limit: 用户请求返回的行数。
    输出:
        清洗后的返回行数。
    """
    return max(1, min(int(limit or MAX_RETURN_ROWS), MAX_RETURN_ROWS))


def _clean_start_index(start_index: int) -> int:
    """把 1-based 起始下标清洗为合法值。

    输入:
        start_index: 用户传入的 1-based 起始下标。
    输出:
        不小于 1 的起始下标。
    """
    return max(1, int(start_index or 1))


def _serialize_value(value: Any) -> Any:
    """把 pandas/numpy 值转换为 JSON 友好的值。

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


def _rows_as_lists(df: pd.DataFrame) -> list[list[Any]]:
    """把 DataFrame 行转换成列表套列表。

    输入:
        df: 待转换 DataFrame。
    输出:
        每行一个列表的二维数组。
    """
    return [[_serialize_value(value) for value in row] for row in df.to_numpy().tolist()]


def _format_bucket(value: Any) -> str:
    """识别单元格内容的大致格式类型。

    输入:
        value: 单元格原始值。
    输出:
        格式类型标签。
    """
    if pd.isna(value):
        return "missing"
    text = str(value).strip()
    if not text:
        return "empty_string"
    if re.fullmatch(r"[-+]?\d+", text):
        return "integer_like"
    if re.fullmatch(r"[-+]?\d*\.\d+", text):
        return "float_like"
    if pd.to_datetime(text, errors="coerce") is not pd.NaT:
        return "datetime_like"
    if re.fullmatch(r"[A-Za-z]+", text):
        return "letters_only"
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return "code_like"
    if re.search(r"[\u4e00-\u9fff]", text):
        return "contains_chinese"
    return "other_text"


@mcp.tool()
def get_rows(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    filter_column: Annotated[
        str | None,
        Field(description="可选。需要筛选的字段名；如果传入，则必须同时传入 filter_value。"),
    ] = None,
    filter_value: Annotated[
        str | None,
        Field(description="可选。筛选字段需要等于的内容，会按字符串形式比较。"),
    ] = None,
    sort_column: Annotated[
        str | None,
        Field(description="可选。需要排序的字段名。"),
    ] = None,
    sort_direction: Annotated[
        Literal["asc", "desc"],
        Field(description="排序方向：asc 表示升序，desc 表示降序。"),
    ] = "desc",
    start_index: Annotated[
        int,
        Field(ge=1, description="1-based 起始下标，表示在筛选/排序后的结果中从第几行开始返回。"),
    ] = 1,
    limit: Annotated[
        int,
        Field(ge=1, le=50, description="最多返回多少行；上限固定为 50。"),
    ] = 50,
) -> dict[str, Any]:
    """读取 CSV 行数据，可同时支持按字段值筛选、按字段排序和分页返回。"""
    tool_name = "get_rows"
    try:
        _log_tool_call(
            tool_name,
            f"file_path={file_path}, filter={filter_column}:{filter_value}, sort={sort_column}:{sort_direction}",
        )
        df = _read_csv(file_path)
        original_row_count = len(df)

        if filter_column:
            _require_column(df, filter_column)
            if filter_value is None:
                raise ValueError("传入 filter_column 时必须同时传入 filter_value。")
            df = df[df[filter_column].astype(str) == str(filter_value)]

        if sort_column:
            _require_column(df, sort_column)
            sort_values = pd.to_numeric(df[sort_column], errors="coerce")
            if sort_values.notna().any():
                df = df.assign(_sort_key=sort_values).sort_values(
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
        start = _clean_start_index(start_index)
        clean_limit = _clean_limit(limit)
        page = df.iloc[start - 1 : start - 1 + clean_limit]

        return {
            "success": True,
            "file_path": file_path,
            "original_row_count": original_row_count,
            "matched_row_count": total_rows,
            "start_index": start,
            "limit": clean_limit,
            "returned_row_count": len(page),
            "has_more": start - 1 + clean_limit < total_rows,
            "filter_column": filter_column,
            "filter_value": filter_value,
            "sort_column": sort_column,
            "sort_direction": sort_direction if sort_column else None,
            "sort_mode": sort_mode,
            "columns": list(df.columns),
            "rows": _rows_as_lists(page),
        }
    except Exception as exc:
        return _error(tool_name, exc)


@mcp.tool()
def profile_value_ratio(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    column_name: Annotated[str, Field(description="需要统计内容占比的字段名。")],
    top_n: Annotated[int, Field(ge=1, le=50, description="返回占比最高的取值数量；上限固定为 50。")] = 20,
) -> dict[str, Any]:
    """统计某个字段的具体内容占比，例如品牌、颜色、地区等类别的占比。"""
    tool_name = "profile_value_ratio"
    try:
        _log_tool_call(tool_name, f"file_path={file_path}, column_name={column_name}, top_n={top_n}")
        df = _read_csv(file_path)
        _require_column(df, column_name)
        total_rows = len(df)
        series = df[column_name]
        counts = series.fillna("__MISSING__").astype(str).value_counts(dropna=False)
        clean_top_n = max(1, min(int(top_n or 20), MAX_RATIO_ITEMS))
        items = []
        for value, count in counts.head(clean_top_n).items():
            label = None if value == "__MISSING__" else value
            items.append(
                {
                    "value": label,
                    "count": int(count),
                    "ratio_pct": round((int(count) / total_rows * 100) if total_rows else 0, 4),
                }
            )
        return {
            "success": True,
            "file_path": file_path,
            "column_name": column_name,
            "total_rows": total_rows,
            "unique_value_count": int(series.nunique(dropna=True)),
            "missing_count": int(series.isna().sum()),
            "returned_item_count": len(items),
            "items": items,
        }
    except Exception as exc:
        return _error(tool_name, exc)


@mcp.tool()
def profile_format_ratio(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    column_name: Annotated[str, Field(description="需要统计格式占比的字段名。")],
) -> dict[str, Any]:
    """统计某个字段的格式类型占比，例如空值、整数样式、浮点样式、日期样式、文本样式等。"""
    tool_name = "profile_format_ratio"
    try:
        _log_tool_call(tool_name, f"file_path={file_path}, column_name={column_name}")
        df = _read_csv(file_path)
        _require_column(df, column_name)
        total_rows = len(df)
        buckets = df[column_name].map(_format_bucket).value_counts(dropna=False)
        items = [
            {
                "format": str(format_name),
                "count": int(count),
                "ratio_pct": round((int(count) / total_rows * 100) if total_rows else 0, 4),
            }
            for format_name, count in buckets.items()
        ]
        return {
            "success": True,
            "file_path": file_path,
            "column_name": column_name,
            "total_rows": total_rows,
            "items": items,
        }
    except Exception as exc:
        return _error(tool_name, exc)


@mcp.tool()
def add_columns_sum(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    left_column: Annotated[str, Field(description="相加运算的左侧数值字段名。")],
    right_column: Annotated[str, Field(description="相加运算的右侧数值字段名。")],
    new_column: Annotated[
        str,
        Field(min_length=1, max_length=80, description="新增字段名，由 Agent 根据业务含义命名。"),
    ],
    output_file_path: Annotated[
        str | None,
        Field(description="可选。写出 CSV 路径；不传则在原文件旁生成一个带新字段名后缀的新文件。"),
    ] = None,
) -> dict[str, Any]:
    """把 CSV 中两列转换为数值后相加，并把结果作为新列写入新的 CSV 文件。"""
    tool_name = "add_columns_sum"
    try:
        _log_tool_call(tool_name, f"file_path={file_path}, {left_column}+{right_column}->{new_column}")
        df = _read_csv(file_path)
        _require_column(df, left_column)
        _require_column(df, right_column)
        if new_column in df.columns:
            raise ValueError(f"新增字段名已存在：{new_column}")

        left_values = pd.to_numeric(df[left_column], errors="coerce")
        right_values = pd.to_numeric(df[right_column], errors="coerce")
        invalid_count = int((left_values.isna() | right_values.isna()).sum())
        df[new_column] = left_values + right_values

        input_path = Path(file_path)
        if output_file_path:
            output_path = Path(output_file_path)
        else:
            safe_column = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff-]+", "_", new_column).strip("_") or "calculated"
            output_path = input_path.with_name(f"{input_path.stem}_{safe_column}{input_path.suffix}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False, encoding="utf-8-sig")

        preview = df[[left_column, right_column, new_column]].head(MAX_RETURN_ROWS)
        return {
            "success": True,
            "input_file_path": file_path,
            "output_file_path": str(output_path),
            "left_column": left_column,
            "right_column": right_column,
            "new_column": new_column,
            "row_count": len(df),
            "invalid_operand_row_count": invalid_count,
            "preview_columns": [left_column, right_column, new_column],
            "preview_rows": _rows_as_lists(preview),
        }
    except Exception as exc:
        return _error(tool_name, exc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
