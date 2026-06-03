"""节点输出落盘工具。

这个文件负责把每个 LangGraph 节点的原始输出、结构化输出和错误信息保存到本地文件，
便于中途失败后排查问题。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


NODE_OUTPUT_DIR = Path("node_outputs")
SENSITIVE_KEYS = {"password", "password_encrypted", "api_key", "token", "secret"}


def _safe_name(value: str) -> str:
    """把节点名或标签转换成适合文件名的字符串。

    输入:
        value: 原始节点名或标签。
    输出:
        只包含字母、数字、下划线和短横线的安全文件名片段。
    """
    cleaned = re.sub(r"[^0-9a-zA-Z_\-]+", "_", value.strip())
    return cleaned.strip("_") or "unknown"


def _to_jsonable(value: Any) -> Any:
    """把任意 Python 对象转换成可写入 JSON 的对象。

    输入:
        value: 任意 Python 对象，可能包含 Pydantic 模型、Path、datetime 或普通容器。
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
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def allocate_node_step(task_id: str, node_name: str) -> int:
    """为一次节点执行分配递增步号。

    输入:
        task_id: 当前任务 ID。
        node_name: 当前节点名。
    输出:
        本次节点执行对应的步号，从 1 开始递增。
    """
    task_dir = NODE_OUTPUT_DIR / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    max_step = 0
    for path in task_dir.iterdir():
        match = re.match(r"^(\d{3,})_", path.name)
        if match:
            max_step = max(max_step, int(match.group(1)))
    return max_step + 1


def _node_step_dir(task_id: str, step_number: int, node_name: str) -> Path:
    """返回当前节点执行步的产物目录。

    输入:
        task_id: 当前任务 ID。
        step_number: 当前节点执行步号。
        node_name: 当前节点名。
    输出:
        `node_outputs/{task_id}/{step}_{node_name}` 目录路径。
    """
    return NODE_OUTPUT_DIR / task_id / f"{step_number:03d}_{_safe_name(node_name)}"


def _write_text_atomic(path: Path, content: str) -> None:
    """用临时文件原子替换的方式写入文本。

    输入:
        path: 最终文件路径。
        content: 要写入的文本内容。
    输出:
        无返回值。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


def save_node_json(
    task_id: Optional[str],
    step_number: Optional[int],
    node_name: str,
    label: str,
    payload: Any,
) -> Optional[str]:
    """保存节点 JSON 输出。

    输入:
        task_id: 当前任务 ID；为空时不保存。
        step_number: 当前节点执行步号；为空时不保存。
        node_name: 当前节点名。
        label: 文件标签，例如 output、error。
        payload: 要保存的对象。
    输出:
        成功写入时返回文件路径；否则返回 None。
    """
    if not task_id or not step_number:
        return None
    try:
        path = _node_step_dir(task_id, int(step_number), node_name) / f"{_safe_name(label)}.json"
        wrapped = {
            "_node_output": {
                "task_id": task_id,
                "step_number": step_number,
                "node_name": node_name,
                "label": label,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
            },
            "payload": _to_jsonable(payload),
        }
        _write_text_atomic(path, json.dumps(wrapped, ensure_ascii=False, indent=2))
        return str(path)
    except Exception as exc:
        print(f"保存节点 JSON 输出失败：{node_name} {label}: {exc}")
        return None


def save_node_text(
    task_id: Optional[str],
    step_number: Optional[int],
    node_name: str,
    label: str,
    content: str,
) -> Optional[str]:
    """保存节点文本输出。

    输入:
        task_id: 当前任务 ID；为空时不保存。
        step_number: 当前节点执行步号；为空时不保存。
        node_name: 当前节点名。
        label: 文件标签，例如 raw_llm、raw_report。
        content: 要保存的文本内容。
    输出:
        成功写入时返回文件路径；否则返回 None。
    """
    if not task_id or not step_number:
        return None
    try:
        path = _node_step_dir(task_id, int(step_number), node_name) / f"{_safe_name(label)}.txt"
        _write_text_atomic(path, content or "")
        return str(path)
    except Exception as exc:
        print(f"保存节点文本输出失败：{node_name} {label}: {exc}")
        return None
