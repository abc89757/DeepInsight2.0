"""Skill 场景定性任务持久化同步。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.task_persistence import normalize_task_status
from system_db import get_system_db, json_dumps


def update_skill_scene_direction_task_stage(
    task_id: str,
    stage: str,
    message: Optional[str],
    status: str = "running",
    error_message: Optional[str] = None,
) -> None:
    """更新场景定性任务通用主表状态。"""
    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tasks
                SET
                    status = %s,
                    current_stage = %s,
                    message = %s,
                    error_message = %s,
                    started_at = CASE
                        WHEN started_at IS NULL AND %s IN ('running', 'succeeded', 'failed')
                        THEN NOW()
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN finished_at IS NULL AND %s IN ('succeeded', 'failed', 'cancelled')
                        THEN NOW()
                        ELSE finished_at
                    END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    stage,
                    message,
                    error_message,
                    status,
                    status,
                    task_id,
                ),
            )


def sync_skill_scene_direction_state_to_db(task_id: str, state: Dict[str, Any]) -> None:
    """同步场景定性 graph state 到数据库。"""
    if not state:
        return

    status = normalize_task_status(state.get("status"), state.get("error"))
    stage = state.get("stage") or state.get("current_stage") or "scene_direction"
    message = state.get("message") or state.get("scene_direction") or state.get("judge_message")
    error_message = state.get("error")

    completed_rounds = int(state.get("debate_round") or 0)
    if not state.get("should_finish"):
        completed_rounds = max(0, completed_rounds - 1)

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE tasks
                SET
                    status = %s,
                    current_stage = %s,
                    message = %s,
                    error_message = %s,
                    started_at = CASE
                        WHEN started_at IS NULL AND %s IN ('running', 'succeeded', 'failed')
                        THEN NOW()
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN finished_at IS NULL AND %s IN ('succeeded', 'failed', 'cancelled')
                        THEN NOW()
                        ELSE finished_at
                    END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    stage,
                    message,
                    error_message,
                    status,
                    status,
                    task_id,
                ),
            )
            cursor.execute(
                """
                UPDATE skill_scene_direction_tasks
                SET
                    completed_debate_rounds = %s,
                    judge_decision = %s,
                    selected_debater_id = %s,
                    context_json = CAST(%s AS JSON),
                    latest_state_json = CAST(%s AS JSON),
                    scene_direction = %s,
                    started_at = CASE
                        WHEN started_at IS NULL THEN NOW()
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN %s IN ('succeeded', 'failed', 'cancelled') THEN NOW()
                        ELSE finished_at
                    END,
                    updated_at = NOW()
                WHERE task_id = %s
                """,
                (
                    completed_rounds,
                    state.get("judge_decision"),
                    state.get("selected_debater_id"),
                    json_dumps(state.get("context", {})),
                    json_dumps(state),
                    state.get("scene_direction"),
                    status,
                    task_id,
                ),
            )

