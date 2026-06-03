"""工具调用审计日志。

这个模块把 Agent 调用工具的输入、输出和错误记录到任务输出目录里，便于分析流程中断后排查工具使用情况。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


SENSITIVE_KEYS = {"password", "password_encrypted", "api_key", "token", "secret"}
TEXT_CONTENT_TYPES = {None, "text"}


def save_tool_call(
    task_id: Optional[str],
    node_name: str,
    tool_name: str,
    arguments: Any,
    result: Any = None,
    error: Optional[str] = None,
) -> Optional[str]:
    """保存一次工具调用记录。

    输入:
        task_id: 当前任务 ID；为空时不保存。
        node_name: 调用工具的 Agent/节点名称。
        tool_name: 工具名称。
        arguments: 工具调用参数。
        result: 工具返回结果。
        error: 工具调用异常信息；没有异常时为空。
    输出:
        成功写入时返回日志文件路径；否则返回 None。
    """
    if not task_id:
        return None

    try:
        log_dir = Path("node_outputs") / task_id
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "tool_calls.jsonl"
        raw_result = _to_jsonable(result)
        normalized_result, result_format, is_mcp_result = normalize_tool_result(raw_result)
        payload = {
            "task_id": task_id,
            "node_name": node_name,
            "tool_name": tool_name,
            "called_at": datetime.now().isoformat(timespec="seconds"),
            "status": "error" if error else "success",
            "arguments": _to_jsonable(arguments),
            "result": normalized_result,
            "raw_result": raw_result,
            "result_format": result_format,
            "is_mcp_result": is_mcp_result,
            "error": error,
        }
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        return str(log_path)
    except Exception as exc:
        print(f"保存工具调用日志失败：{node_name}.{tool_name}: {exc}")
        return None


def load_tool_calls(task_id: Optional[str], node_name: Optional[str] = None) -> list[dict[str, Any]]:
    """读取某个任务的工具调用日志。

    输入:
        task_id: 当前任务 ID；为空时返回空列表。
        node_name: 可选节点名称；传入时只返回该节点的工具调用。
    输出:
        工具调用记录列表；读取失败时返回空列表。
    """
    if not task_id:
        return []

    log_path = Path("node_outputs") / task_id / "tool_calls.jsonl"
    if not log_path.exists():
        return []

    records: list[dict[str, Any]] = []
    try:
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            if node_name and item.get("node_name") != node_name:
                continue
            normalize_tool_call_record(item)
            records.append(item)
    except Exception as exc:
        print(f"读取工具调用日志失败：{task_id}: {exc}")
        return []
    return records


def normalize_tool_call_record(record: dict[str, Any]) -> None:
    """把旧版工具日志中的返回结果补齐为新格式。

    输入:
        record: 从 `tool_calls.jsonl` 读取的一条记录。
    输出:
        无返回值；会就地补充 `raw_result`、归一化后的 `result` 和格式标记。
    """
    if "raw_result" not in record:
        raw_result = record.get("result")
    else:
        raw_result = record.get("raw_result")

    normalized_result, result_format, is_mcp_result = normalize_tool_result(raw_result)
    record["raw_result"] = raw_result
    record["result"] = normalized_result
    record["result_format"] = record.get("result_format") or result_format
    record["is_mcp_result"] = bool(record.get("is_mcp_result", is_mcp_result))


def normalize_tool_result(result: Any) -> tuple[Any, str, bool]:
    """归一化工具返回结果，特别处理 MCP content blocks。

    输入:
        result: 工具原始返回值，已经过 JSON 友好转换。
    输出:
        `(normalized_result, result_format, is_mcp_result)`。
    """
    if result is None:
        return None, "none", False

    if isinstance(result, dict) and isinstance(result.get("content"), list):
        return normalize_mcp_content_blocks(result.get("content") or []), "mcp_content", True

    if isinstance(result, list) and is_mcp_content_blocks(result):
        return normalize_mcp_content_blocks(result), "mcp_content_blocks", True

    if isinstance(result, str):
        parsed = parse_json_text(result)
        if parsed is not result:
            return parsed, "json_string", False
        return result, "text", False

    if isinstance(result, dict):
        return result, "dict", False

    if isinstance(result, list):
        return result, "list", False

    return result, result.__class__.__name__, False


def is_mcp_content_blocks(value: list[Any]) -> bool:
    """判断列表是否像 MCP/LangChain content blocks。"""
    if not value:
        return False
    return all(
        isinstance(item, str)
        or (
            isinstance(item, dict)
            and (
                "type" in item
                or "text" in item
                or "content" in item
                or "json" in item
                or "data" in item
            )
        )
        for item in value
    )


def normalize_mcp_content_blocks(blocks: list[Any]) -> Any:
    """把 MCP content blocks 转成更适合业务节点读取的结果。"""
    values: list[Any] = []
    for block in blocks:
        if isinstance(block, str):
            values.append(parse_json_text(block))
            continue

        if not isinstance(block, dict):
            values.append(_to_jsonable(block))
            continue

        block_type = block.get("type")
        if block_type in TEXT_CONTENT_TYPES:
            text = block.get("text")
            if text is None:
                text = block.get("content")
            if text is not None:
                values.append(parse_json_text(str(text)))
                continue

        if block_type == "json" or "json" in block:
            values.append(block.get("json"))
            continue

        if "data" in block:
            values.append(block.get("data"))
            continue

        values.append(_to_jsonable(block))

    if len(values) == 1:
        return values[0]
    return values


def parse_json_text(text: str) -> Any:
    """尝试把文本解析为 JSON；失败时返回原文本。"""
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return text


def _to_jsonable(value: Any) -> Any:
    """把工具调用参数和结果转换为 JSON 友好对象。

    输入:
        value: 任意 Python 对象。
    输出:
        可被 json.dumps 序列化的对象；敏感字段会被脱敏。
    """
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                result[key_text] = "******" if item else ""
            else:
                result[key_text] = _to_jsonable(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
