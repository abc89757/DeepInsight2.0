"""工具调用审计日志。

这个模块把 Agent 调用工具的输入、输出和错误记录到任务输出目录里，便于分析流程中断后排查工具使用情况。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


SENSITIVE_KEYS = {"password", "password_encrypted", "api_key", "token", "secret"}


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
        payload = {
            "task_id": task_id,
            "node_name": node_name,
            "tool_name": tool_name,
            "called_at": datetime.now().isoformat(timespec="seconds"),
            "status": "error" if error else "success",
            "arguments": _to_jsonable(arguments),
            "result": _to_jsonable(result),
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
            records.append(item)
    except Exception as exc:
        print(f"读取工具调用日志失败：{task_id}: {exc}")
        return []
    return records


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
