"""product_sales 场景的图表生成 MCP 工具。

这个文件提供柱状图、折线图和饼图工具。工具只接收 CSV 文件路径、字段名和图表配置，
由工具自行读取完整数据、绘图、保存图片，并返回结构化图表产物。
"""

from __future__ import annotations

import math
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from mcp.server.fastmcp import FastMCP
from pydantic import Field


plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Arial Unicode MS", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

mcp = FastMCP("product_sales_chart_tools")
LOG_DIR = Path("tool_call_logs")
MAX_TOP_N = 20


def _log_tool_call(tool_name: str, detail: str) -> None:
    """记录图表工具调用日志。

    输入:
        tool_name: 工具名称。
        detail: 调用摘要。
    输出:
        无返回值；日志会写入文件并打印到 stderr。
    """
    message = f"{datetime.now().isoformat(timespec='seconds')} [{tool_name}] {detail}"
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "product_sales_chart_tool_calls.log").open("a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")
    print(f"[product_sales chart tool] {message}", file=sys.stderr, flush=True)


def _error(tool_name: str, exc: Exception) -> dict[str, Any]:
    """把异常转换成工具返回值。

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


def _numeric_series(df: pd.DataFrame, column_name: str) -> pd.Series:
    """读取并转换数值字段。

    输入:
        df: 数据表。
        column_name: 数值字段名。
    输出:
        pandas 数值序列。
    """
    _require_column(df, column_name)
    values = pd.to_numeric(df[column_name], errors="coerce")
    if values.notna().sum() == 0:
        raise ValueError(f"字段无法转换为数值：{column_name}")
    return values


def _safe_filename(value: str, fallback: str) -> str:
    """生成安全文件名。

    输入:
        value: 用户或 Agent 提供的文件名。
        fallback: 空值时使用的备用文件名。
    输出:
        适合保存到本地的文件名，不包含扩展名。
    """
    cleaned = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", str(value or "").strip()).strip("_")
    return cleaned or fallback


def _prepare_output_path(output_dir: str, output_filename: str | None, fallback: str) -> Path:
    """准备图表输出路径。

    输入:
        output_dir: 图表输出目录。
        output_filename: 可选输出文件名。
        fallback: 未提供文件名时使用的备用文件名。
    输出:
        PNG 文件路径。
    """
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    stem = _safe_filename(output_filename or fallback, fallback)
    if stem.lower().endswith(".png"):
        return folder / stem
    return folder / f"{stem}.png"


def _finish_chart(
    fig: Any,
    output_path: Path,
    chart_type: str,
    title: str,
    caption: str,
    data_source: str,
    columns_used: list[str],
    description: str,
    data_note: str,
) -> dict[str, Any]:
    """保存图表并构造结构化返回结果。

    输入:
        fig: matplotlib Figure。
        output_path: 图片输出路径。
        chart_type: 图表类型。
        title: 图表标题。
        caption: 图表说明。
        data_source: 数据来源文件。
        columns_used: 使用字段。
        description: 图表结论描述。
        data_note: 数据限制说明。
    输出:
        可供 ChartGeneratorNode 整理的图表产物字典。
    """
    fig.tight_layout()
    fig.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close(fig)
    return {
        "success": True,
        "chart_type": chart_type,
        "title": title,
        "file_path": str(output_path),
        "data_source": data_source,
        "columns_used": columns_used,
        "description": description,
        "caption": caption,
        "data_note": data_note,
    }


def _clean_top_n(top_n: int) -> int:
    """清洗 Top N 参数。

    输入:
        top_n: 用户传入的 Top N。
    输出:
        限制在 1 到 MAX_TOP_N 之间的整数。
    """
    return max(1, min(int(top_n or 10), MAX_TOP_N))


def _to_float(value: Any) -> float | None:
    """把值转换成普通浮点数。

    输入:
        value: 原始值。
    输出:
        可 JSON 序列化的浮点数；无效时返回 None。
    """
    try:
        result = float(value)
    except Exception:
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


@mcp.tool()
def draw_bar_chart(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    output_dir: Annotated[str, Field(description="图片输出目录，通常是当前任务的 charts 目录。")],
    x_column: Annotated[str, Field(description="柱状图横轴类别字段名。")],
    y_column: Annotated[str, Field(description="柱状图纵轴数值字段名。")],
    title: Annotated[str, Field(description="图表标题，必须说明分析对象、指标和维度。")],
    caption: Annotated[str, Field(description="报告中放在图下方的 1-3 句话说明。")],
    output_filename: Annotated[str | None, Field(description="可选输出文件名，不传则根据标题生成。")] = None,
    top_n: Annotated[int, Field(ge=1, le=20, description="最多展示多少个类别；上限 20。")] = 10,
    sort_direction: Annotated[Literal["asc", "desc"], Field(description="按 y_column 排序方向。")] = "desc",
    horizontal: Annotated[bool, Field(description="是否使用横向柱状图；类别名较长时建议为 true。")] = True,
) -> dict[str, Any]:
    """根据 CSV 的类别字段和数值字段绘制柱状图，适合类别对比、排名和 Top N 展示。"""
    tool_name = "draw_bar_chart"
    try:
        _log_tool_call(tool_name, f"file_path={file_path}, x={x_column}, y={y_column}")
        df = _read_csv(file_path)
        _require_column(df, x_column)
        values = _numeric_series(df, y_column)
        data = df.assign(_value=values).dropna(subset=[x_column, "_value"])
        data = data.sort_values("_value", ascending=sort_direction == "asc").head(_clean_top_n(top_n))
        if data.empty:
            raise ValueError("没有可绘制的数据。")

        fig_height = max(4, min(10, 0.42 * len(data) + 1.5))
        fig, ax = plt.subplots(figsize=(9, fig_height if horizontal else 5))
        labels = data[x_column].astype(str)
        numbers = data["_value"]
        if horizontal:
            ax.barh(labels, numbers, color="#3b82f6")
            ax.invert_yaxis()
            ax.set_xlabel(y_column)
            ax.set_ylabel(x_column)
        else:
            ax.bar(labels, numbers, color="#3b82f6")
            ax.set_xlabel(x_column)
            ax.set_ylabel(y_column)
            plt.setp(ax.get_xticklabels(), rotation=35, ha="right")
        ax.set_title(title)
        ax.grid(axis="x" if horizontal else "y", alpha=0.22)

        output_path = _prepare_output_path(output_dir, output_filename, title)
        data_note = f"展示按 {y_column} 排序后的 Top {len(data)} 项。"
        return _finish_chart(
            fig=fig,
            output_path=output_path,
            chart_type="bar",
            title=title,
            caption=caption,
            data_source=file_path,
            columns_used=[x_column, y_column],
            description=caption,
            data_note=data_note,
        )
    except Exception as exc:
        return _error(tool_name, exc)


@mcp.tool()
def draw_line_chart(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    output_dir: Annotated[str, Field(description="图片输出目录，通常是当前任务的 charts 目录。")],
    x_column: Annotated[str, Field(description="横轴字段名，通常是日期、时间或有序阶段字段。")],
    y_column: Annotated[str, Field(description="纵轴数值字段名。")],
    title: Annotated[str, Field(description="图表标题，必须说明分析对象、指标和时间范围。")],
    caption: Annotated[str, Field(description="报告中放在图下方的 1-3 句话说明。")],
    output_filename: Annotated[str | None, Field(description="可选输出文件名，不传则根据标题生成。")] = None,
    series_column: Annotated[str | None, Field(description="可选。多条折线的分组字段名。")] = None,
) -> dict[str, Any]:
    """根据 CSV 的有序字段和数值字段绘制折线图，适合趋势变化展示。"""
    tool_name = "draw_line_chart"
    try:
        _log_tool_call(tool_name, f"file_path={file_path}, x={x_column}, y={y_column}, series={series_column}")
        df = _read_csv(file_path)
        _require_column(df, x_column)
        values = _numeric_series(df, y_column)
        data = df.assign(_value=values).dropna(subset=[x_column, "_value"])
        if data.empty:
            raise ValueError("没有可绘制的数据。")

        parsed_x = pd.to_datetime(data[x_column], errors="coerce")
        use_datetime = parsed_x.notna().sum() >= max(2, len(data) * 0.6)
        data = data.assign(_x=parsed_x if use_datetime else data[x_column].astype(str))
        data = data.sort_values("_x")

        fig, ax = plt.subplots(figsize=(9, 5))
        columns_used = [x_column, y_column]
        if series_column:
            _require_column(data, series_column)
            columns_used.append(series_column)
            for label, group in data.groupby(series_column, dropna=False):
                group = group.sort_values("_x")
                ax.plot(group["_x"], group["_value"], marker="o", linewidth=1.8, label=str(label))
            ax.legend(loc="best")
        else:
            ax.plot(data["_x"], data["_value"], marker="o", linewidth=1.8, color="#2563eb")

        ax.set_title(title)
        ax.set_xlabel(x_column)
        ax.set_ylabel(y_column)
        ax.grid(alpha=0.22)
        if not use_datetime:
            plt.setp(ax.get_xticklabels(), rotation=35, ha="right")

        output_path = _prepare_output_path(output_dir, output_filename, title)
        data_note = "折线图按横轴字段排序；如果横轴不是时间字段，只能解释为有序对比，不能解释为时间趋势。"
        return _finish_chart(
            fig=fig,
            output_path=output_path,
            chart_type="line",
            title=title,
            caption=caption,
            data_source=file_path,
            columns_used=columns_used,
            description=caption,
            data_note=data_note,
        )
    except Exception as exc:
        return _error(tool_name, exc)


@mcp.tool()
def draw_pie_chart(
    file_path: Annotated[str, Field(description="CSV 文件路径，必须传入。")],
    output_dir: Annotated[str, Field(description="图片输出目录，通常是当前任务的 charts 目录。")],
    label_column: Annotated[str, Field(description="饼图类别字段名。")],
    value_column: Annotated[str, Field(description="饼图数值字段名。")],
    title: Annotated[str, Field(description="图表标题，必须说明分析对象和占比口径。")],
    caption: Annotated[str, Field(description="报告中放在图下方的 1-3 句话说明。")],
    output_filename: Annotated[str | None, Field(description="可选输出文件名，不传则根据标题生成。")] = None,
    top_n: Annotated[int, Field(ge=1, le=10, description="最多展示多少个类别；饼图建议不超过 5，硬上限 10。")] = 5,
) -> dict[str, Any]:
    """根据 CSV 的类别字段和数值字段绘制饼图，适合少量类别的整体占比展示。"""
    tool_name = "draw_pie_chart"
    try:
        _log_tool_call(tool_name, f"file_path={file_path}, label={label_column}, value={value_column}")
        df = _read_csv(file_path)
        _require_column(df, label_column)
        values = _numeric_series(df, value_column)
        data = df.assign(_value=values).dropna(subset=[label_column, "_value"])
        data = data[data["_value"] > 0]
        if data.empty:
            raise ValueError("没有可绘制的正数占比数据。")

        clean_top_n = max(1, min(int(top_n or 5), 10))
        grouped = data.groupby(label_column, dropna=False)["_value"].sum().sort_values(ascending=False)
        top = grouped.head(clean_top_n)
        other_sum = grouped.iloc[clean_top_n:].sum()
        if other_sum > 0:
            top.loc["其他"] = other_sum

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.pie(
            top.values,
            labels=[str(item) for item in top.index],
            autopct="%1.1f%%",
            startangle=90,
            counterclock=False,
        )
        ax.axis("equal")
        ax.set_title(title)

        output_path = _prepare_output_path(output_dir, output_filename, title)
        data_note = f"饼图展示前 {min(clean_top_n, len(grouped))} 个类别；其余类别合并为'其他'。"
        return _finish_chart(
            fig=fig,
            output_path=output_path,
            chart_type="pie",
            title=title,
            caption=caption,
            data_source=file_path,
            columns_used=[label_column, value_column],
            description=caption,
            data_note=data_note,
        )
    except Exception as exc:
        return _error(tool_name, exc)


if __name__ == "__main__":
    mcp.run(transport="stdio")
