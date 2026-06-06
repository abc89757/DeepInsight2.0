from __future__ import annotations

import traceback

from schemas import AnalysisTaskContext
from system_db import now_str
from task.analysis_task_runner import run_analysis_task
from task_store import TASK_STORE

from services.task_persistence import sync_task_state_to_db


def run_analysis_task_with_persistence(
    task_id: str,
    request: AnalysisTaskContext,
) -> None:
    """
    过渡版后台任务包装器。

    现在 task_runner 仍然写 TASK_STORE；这个包装器保证任务结束后同步一次 MySQL。
    """
    try:
        run_analysis_task(
            task_id=task_id,
            request=request,
            task_store=TASK_STORE,
        )
    except Exception as exc:
        state = TASK_STORE.setdefault(task_id, {})
        state.update(
            {
                "task_id": task_id,
                "status": "failed",
                "stage": state.get("stage") or "unknown",
                "message": "任务执行失败",
                "error": str(exc),
                "updated_at": now_str(),
            }
        )
        traceback.print_exc()
    finally:
        state = TASK_STORE.get(task_id)
        if state:
            sync_task_state_to_db(task_id, state)
