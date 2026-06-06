"""Skill 沉淀任务创建服务。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from graph.skill_distillation.context import SKILL_TYPE_FILE_NAMES
from system_db import get_system_db, now_str


SKILL_CANDIDATE_ROOT = Path("skill_candidates")


def default_target_skill_name(source_analysis_task_id: str) -> str:
    """根据来源分析任务 ID 生成默认候选 Skill 名称。"""
    return f"skill_{source_analysis_task_id[:8]}"


def create_skill_distillation_task(
    source_analysis_task_id: str,
    *,
    task_id: Optional[str] = None,
    target_skill_name: Optional[str] = None,
    target_skill_display_name: Optional[str] = None,
    max_rounds: int = 3,
    model_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Dict[str, Any]:
    """创建一次 Skill 沉淀任务及五类 Skill 文件子记录。

    输入:
        source_analysis_task_id: 来源分析任务 ID。
        task_id: 可选沉淀任务 ID；为空时自动生成。
        target_skill_name: 目标 Skill 文件夹名。
        target_skill_display_name: 目标 Skill 展示名。
        max_rounds: 单个 Skill 文件最大迭代轮次。
        model_id/model_name: 本次任务使用的模型信息快照。

    输出:
        适合放入 TASK_STORE 的沉淀任务状态字典。
    """
    resolved_task_id = task_id or uuid4().hex
    resolved_skill_name = (target_skill_name or "").strip() or default_target_skill_name(source_analysis_task_id)
    candidate_dir = str(SKILL_CANDIDATE_ROOT / resolved_task_id)
    now = now_str()
    message = "Skill 沉淀任务已创建，等待后台流程执行。"

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
                    %s, 'skill_distillation', 'pending', 'waiting', %s,
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
            for skill_type in SKILL_TYPE_FILE_NAMES:
                cursor.execute(
                    """
                    INSERT INTO skill_distillation_tasks (
                        task_id, skill_type, source_analysis_task_id,
                        target_skill_name, target_skill_display_name,
                        candidate_dir, max_rounds, completed_rounds,
                        created_at, updated_at
                    )
                    VALUES (
                        %s, %s, %s,
                        %s, %s,
                        %s, %s, 0,
                        NOW(), NOW()
                    )
                    """,
                    (
                        resolved_task_id,
                        skill_type,
                        source_analysis_task_id,
                        resolved_skill_name,
                        target_skill_display_name,
                        candidate_dir,
                        max_rounds,
                    ),
                )

    return {
        "task_id": resolved_task_id,
        "id": resolved_task_id,
        "task_type": "skill_distillation",
        "source_analysis_task_id": source_analysis_task_id,
        "target_skill_name": resolved_skill_name,
        "target_skill_display_name": target_skill_display_name,
        "candidate_dir": candidate_dir,
        "status": "pending",
        "stage": "waiting",
        "current_stage": "waiting",
        "message": message,
        "max_rounds": max_rounds,
        "created_at": now,
        "updated_at": now,
        "error": None,
        "skill_results": {},
    }

