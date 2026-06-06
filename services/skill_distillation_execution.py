"""Skill 沉淀任务执行包装器。"""

from __future__ import annotations

import traceback
from typing import Optional

from services.skill_distillation_persistence import sync_skill_distillation_task_state_to_db
from services.skill_distillation_task_service import create_skill_distillation_task
from system_db import now_str
from task.skill_distillation_runner import run_skill_distillation_task
from task_store import TASK_STORE


def run_skill_distillation_task_with_persistence(
    task_id: str,
    source_analysis_task_id: str,
    *,
    target_skill_name: Optional[str] = None,
    max_rounds: int = 3,
    max_debate_rounds: int = 3,
    reference_skill_name: str = "product_sales",
    promote_to_skills: bool = True,
    overwrite_existing: bool = False,
) -> None:
    """运行已创建的 Skill 沉淀任务，并在结束后同步状态。"""
    try:
        run_skill_distillation_task(
            task_id=task_id,
            source_analysis_task_id=source_analysis_task_id,
            task_store=TASK_STORE,
            target_skill_name=target_skill_name,
            max_rounds=max_rounds,
            max_debate_rounds=max_debate_rounds,
            reference_skill_name=reference_skill_name,
            promote_to_skills=promote_to_skills,
            overwrite_existing=overwrite_existing,
        )
    except Exception as exc:
        state = TASK_STORE.setdefault(task_id, {})
        state.update(
            {
                "task_id": task_id,
                "task_type": "skill_distillation",
                "source_analysis_task_id": source_analysis_task_id,
                "target_skill_name": target_skill_name,
                "status": "failed",
                "stage": state.get("stage") or "unknown",
                "message": "Skill 沉淀任务执行失败。",
                "error": str(exc),
                "updated_at": now_str(),
            }
        )
        sync_skill_distillation_task_state_to_db(task_id, state)
        traceback.print_exc()
    finally:
        state = TASK_STORE.get(task_id)
        if state:
            sync_skill_distillation_task_state_to_db(task_id, state)


def create_and_run_skill_distillation_task(
    source_analysis_task_id: str,
    *,
    target_skill_name: Optional[str] = None,
    target_skill_display_name: Optional[str] = None,
    max_rounds: int = 3,
    max_debate_rounds: int = 3,
    reference_skill_name: str = "product_sales",
    promote_to_skills: bool = True,
    overwrite_existing: bool = False,
) -> str:
    """创建并同步执行一次 Skill 沉淀任务，返回沉淀任务 ID。"""
    task = create_skill_distillation_task(
        source_analysis_task_id=source_analysis_task_id,
        target_skill_name=target_skill_name,
        target_skill_display_name=target_skill_display_name,
        max_rounds=max_rounds,
    )
    task_id = task["task_id"]
    TASK_STORE[task_id] = task
    run_skill_distillation_task_with_persistence(
        task_id=task_id,
        source_analysis_task_id=source_analysis_task_id,
        target_skill_name=task.get("target_skill_name"),
        max_rounds=max_rounds,
        max_debate_rounds=max_debate_rounds,
        reference_skill_name=reference_skill_name,
        promote_to_skills=promote_to_skills,
        overwrite_existing=overwrite_existing,
    )
    return task_id
