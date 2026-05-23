"""分析任务实时事件总线。

这个文件提供一个轻量的内存事件总线，用于把后台 LangGraph 执行过程通过 SSE 推送给前端。
"""

from __future__ import annotations

import json
import queue
from decimal import Decimal
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator


_TASK_EVENT_QUEUES: dict[str, list["queue.Queue[Dict[str, Any] | None]"]] = {}
_TASK_EVENT_HISTORY: dict[str, list[Dict[str, Any]]] = {}
_MAX_HISTORY_EVENTS = 200


def publish_task_event(task_id: str | None, event_type: str, payload: Dict[str, Any] | None = None) -> None:
    """发布一条任务实时事件。

    输入:
        task_id: 当前任务 ID；为空时不会发布。
        event_type: 事件类型，例如 `node_started`、`agent_delta`。
        payload: 事件附加数据。
    输出:
        无返回值；事件会写入内存队列和短历史。
    """
    if not task_id:
        return

    event = to_jsonable({
        "task_id": task_id,
        "type": event_type,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        **(payload or {}),
    })

    history = _TASK_EVENT_HISTORY.setdefault(task_id, [])
    history.append(event)
    if len(history) > _MAX_HISTORY_EVENTS:
        del history[: len(history) - _MAX_HISTORY_EVENTS]

    for event_queue in list(_TASK_EVENT_QUEUES.get(task_id, [])):
        event_queue.put(event)


def subscribe_task_events(task_id: str) -> Iterator[Dict[str, Any]]:
    """订阅指定任务的实时事件。

    输入:
        task_id: 当前任务 ID。
    输出:
        阻塞迭代器；每次产出一条事件字典，收到关闭信号后结束。
    """
    event_queue: "queue.Queue[Dict[str, Any] | None]" = queue.Queue()
    _TASK_EVENT_QUEUES.setdefault(task_id, []).append(event_queue)

    for event in _TASK_EVENT_HISTORY.get(task_id, []):
        yield event

    try:
        while True:
            event = event_queue.get()
            if event is None:
                break
            yield event
    finally:
        queues = _TASK_EVENT_QUEUES.get(task_id, [])
        if event_queue in queues:
            queues.remove(event_queue)
        if not queues:
            _TASK_EVENT_QUEUES.pop(task_id, None)


def close_task_events(task_id: str | None) -> None:
    """关闭指定任务的事件流。

    输入:
        task_id: 当前任务 ID；为空时不处理。
    输出:
        无返回值；如果存在订阅队列，会放入关闭信号。
    """
    if not task_id:
        return
    for event_queue in list(_TASK_EVENT_QUEUES.get(task_id, [])):
        event_queue.put(None)


def format_sse_event(event: Dict[str, Any]) -> str:
    """把事件字典格式化成 SSE 文本。

    输入:
        event: 事件字典。
    输出:
        符合 Server-Sent Events 协议的文本块。
    """
    event_type = str(event.get("type") or "message")
    data = json.dumps(to_jsonable(event), ensure_ascii=False)
    return f"event: {event_type}\ndata: {data}\n\n"


def to_jsonable(value: Any) -> Any:
    """把事件载荷转换成 JSON 可序列化对象。

    输入:
        value: 任意事件载荷，可能包含 Decimal、datetime、Path 或嵌套容器。
    输出:
        可被 `json.dumps` 序列化的对象。
    """
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return to_jsonable(value.dict())
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, Path)):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
