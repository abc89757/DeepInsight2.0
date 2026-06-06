"""Skill 沉淀工作流状态定义。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class SkillDistillationState(TypedDict, total=False):
    """单个 Skill 文件沉淀 graph 的共享状态。"""

    task_id: str
    distillation_task_id: str
    source_analysis_task_id: str

    skill_type: str
    file_name: str
    artifact_spec: Dict[str, Any]
    context: Dict[str, Any]
    reference_skill_content: str
    scene_direction: str

    round_index: int
    max_rounds: int

    scene_mining_message: str
    writer_message: str
    markdown_content: str
    evaluation_message: str
    evaluation_result: Dict[str, Any]
    evaluator_decision: str
    final_score: Optional[float]

    revision_history: List[Dict[str, Any]]
    status: str
    error: Optional[str]
