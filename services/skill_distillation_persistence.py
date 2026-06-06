"""Skill 沉淀任务持久化同步。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from services.task_persistence import normalize_task_status, upsert_task_artifact
from system_db import get_system_db, json_dumps


def update_skill_distillation_task_stage(
    task_id: str,
    stage: str,
    message: Optional[str],
    status: str = "running",
    error_message: Optional[str] = None,
) -> None:
    """更新沉淀任务通用主表状态。"""
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


def sync_skill_artifact_state_to_db(task_id: str, state: Dict[str, Any]) -> None:
    """同步单个 skill_type 的沉淀 state 到扩展表。"""
    skill_type = state.get("skill_type")
    if not skill_type:
        return

    candidate_file_path = state.get("candidate_file_path")
    final_file_path = state.get("final_file_path")
    if candidate_file_path:
        upsert_task_artifact(
            task_id=task_id,
            artifact_type=f"skill_candidate_{skill_type}",
            uri=candidate_file_path,
            mime_type="text/markdown",
            description=f"{skill_type} 候选 Skill 文件",
        )
    if final_file_path:
        upsert_task_artifact(
            task_id=task_id,
            artifact_type=f"skill_final_{skill_type}",
            uri=final_file_path,
            mime_type="text/markdown",
            description=f"{skill_type} 正式 Skill 文件",
        )

    revision_history = state.get("revision_history") or []
    completed_rounds = len(revision_history) or int(state.get("round_index") or 0)
    evaluation_result = state.get("evaluation_result") or {}
    mining_result = {
        "scene_direction": state.get("scene_direction", ""),
        "scene_mining_message": state.get("scene_mining_message", ""),
    }

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE skill_distillation_tasks
                SET
                    target_skill_name = COALESCE(%s, target_skill_name),
                    candidate_file_path = COALESCE(%s, candidate_file_path),
                    final_file_path = COALESCE(%s, final_file_path),
                    completed_rounds = %s,
                    final_score = %s,
                    evaluator_decision = %s,
                    context_json = CAST(%s AS JSON),
                    latest_state_json = CAST(%s AS JSON),
                    mining_result_json = CAST(%s AS JSON),
                    generated_content = %s,
                    evaluation_json = CAST(%s AS JSON),
                    started_at = CASE
                        WHEN started_at IS NULL THEN NOW()
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN %s IN ('accept', 'max_rounds_reached', 'reject') THEN NOW()
                        ELSE finished_at
                    END,
                    updated_at = NOW()
                WHERE task_id = %s
                  AND skill_type = %s
                """,
                (
                    state.get("target_skill_name"),
                    candidate_file_path,
                    final_file_path,
                    completed_rounds,
                    state.get("final_score"),
                    state.get("evaluator_decision"),
                    json_dumps(state.get("context", {})),
                    json_dumps(state),
                    json_dumps(mining_result),
                    state.get("markdown_content"),
                    json_dumps(evaluation_result),
                    state.get("evaluator_decision"),
                    task_id,
                    skill_type,
                ),
            )


def sync_skill_distillation_task_state_to_db(task_id: str, state: Dict[str, Any]) -> None:
    """同步沉淀任务总状态与当前 skill_type 状态。"""
    if not state:
        return

    status = normalize_task_status(state.get("status"), state.get("error"))
    stage = state.get("stage") or state.get("current_stage") or state.get("skill_type") or "running"
    message = state.get("message")
    error_message = state.get("error")

    update_skill_distillation_task_stage(
        task_id=task_id,
        stage=stage,
        message=message,
        status=status,
        error_message=error_message,
    )
    sync_skill_artifact_state_to_db(task_id, state)
