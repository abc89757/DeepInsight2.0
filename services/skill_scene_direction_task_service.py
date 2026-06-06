"""Skill 场景定性任务创建服务。"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

from system_db import get_system_db, now_str


def create_skill_scene_direction_task(
    *,
    distillation_task_id: str,
    source_analysis_task_id: str,
    task_id: Optional[str] = None,
    max_debate_rounds: int = 3,
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """创建一次 Skill 场景定性任务。"""
    resolved_task_id = task_id or uuid4().hex
    now = now_str()
    message = "Skill 场景定性任务已创建，等待辩论流程执行。"

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, task_type, status, current_stage, message,
                    error_message, model_id, model_name,
                    created_at, updated_at
                )
                VALUES (
                    %s, 'skill_scene_direction', 'pending', 'waiting', %s,
                    NULL, %s, %s,
                    NOW(), NOW()
                )
                """,
                (
                    resolved_task_id,
                    message,
                    model_id,
                    model_name,
                ),
            )
            cursor.execute(
                """
                INSERT INTO skill_scene_direction_tasks (
                    task_id, distillation_task_id, source_analysis_task_id,
                    max_debate_rounds, completed_debate_rounds,
                    created_at, updated_at
                )
                VALUES (
                    %s, %s, %s,
                    %s, 0,
                    NOW(), NOW()
                )
                """,
                (
                    resolved_task_id,
                    distillation_task_id,
                    source_analysis_task_id,
                    max_debate_rounds,
                ),
            )

    return {
        "task_id": resolved_task_id,
        "id": resolved_task_id,
        "task_type": "skill_scene_direction",
        "distillation_task_id": distillation_task_id,
        "source_analysis_task_id": source_analysis_task_id,
        "status": "pending",
        "stage": "waiting",
        "current_stage": "waiting",
        "message": message,
        "max_debate_rounds": max_debate_rounds,
        "created_at": now,
        "updated_at": now,
        "error": None,
    }

