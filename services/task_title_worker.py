from __future__ import annotations

import threading
import traceback

from services.task_events import publish_task_event
from services.task_persistence import update_task_title
from services.task_title import fallback_task_title, generate_task_title
from system_db import now_str
from task_store import TASK_STORE


DEFAULT_TASK_TITLE = "New Task"


def start_task_title_generation(task_id: str, question: str) -> None:
    """Generate a task title in a separate daemon thread."""
    thread = threading.Thread(
        target=generate_and_update_task_title,
        args=(task_id, question),
        name=f"task-title-{task_id[:8]}",
        daemon=True,
    )
    thread.start()


def generate_and_update_task_title(task_id: str, question: str) -> None:
    """Generate a title, persist it, and notify connected clients."""
    try:
        title = generate_task_title(question) or fallback_task_title(question)
        update_task_title(task_id, title)

        task = TASK_STORE.get(task_id)
        if task is not None:
            task["title"] = title
            task["updated_at"] = now_str()

        publish_task_event(
            task_id,
            "task_title_updated",
            {
                "title": title,
            },
        )
    except Exception:
        print(f"生成任务 {task_id} 标题失败：")
        traceback.print_exc()
