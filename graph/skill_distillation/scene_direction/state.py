"""Skill 场景定性 graph 状态定义。"""

from __future__ import annotations

from typing import Any, Dict, Optional, TypedDict


class SceneDirectionState(TypedDict, total=False):
    """场景定性辩论 graph 的共享状态。"""

    task_id: str
    scene_direction_task_id: str
    distillation_task_id: str
    source_analysis_task_id: str

    context: Dict[str, Any]
    reference_skill_content: str

    debate_round: int
    max_debate_rounds: int
    debater_ids: list[str]

    judge_decision: str
    judge_message: str
    should_finish: bool

    selected_debater_id: Optional[str]
    scene_direction: str

    status: str
    error: Optional[str]

    debate_business_context_1: str
    debate_business_context_2: str
    debate_business_context_3: str
    debate_business_context_4: str
    debate_business_context_5: str
    debate_business_context_6: str
    debate_business_context_7: str
    debate_business_context_8: str
    debate_business_context_9: str
    debate_business_context_10: str

    debate_data_object_1: str
    debate_data_object_2: str
    debate_data_object_3: str
    debate_data_object_4: str
    debate_data_object_5: str
    debate_data_object_6: str
    debate_data_object_7: str
    debate_data_object_8: str
    debate_data_object_9: str
    debate_data_object_10: str

    debate_problem_purpose_1: str
    debate_problem_purpose_2: str
    debate_problem_purpose_3: str
    debate_problem_purpose_4: str
    debate_problem_purpose_5: str
    debate_problem_purpose_6: str
    debate_problem_purpose_7: str
    debate_problem_purpose_8: str
    debate_problem_purpose_9: str
    debate_problem_purpose_10: str

    judge_1: str
    judge_2: str
    judge_3: str
    judge_4: str
    judge_5: str
    judge_6: str
    judge_7: str
    judge_8: str
    judge_9: str
    judge_10: str
