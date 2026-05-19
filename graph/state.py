"""LangGraph 状态定义。

这个文件集中描述数据分析工作流里各个节点共享、读取和写入的 state 字段。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GraphState(TypedDict, total=False):
    """数据分析图的共享状态。

    输入:
        LangGraph 在节点之间传递的字典状态。
    输出:
        TypedDict 只提供类型约束，不在运行时产生具体输出。
    """

    task_id: str
    question: str
    database: Any
    database_alias: str
    output_dir: str

    schema_info: str

    available_skills: List[Dict[str, Any]]
    selected_skill_name: str
    skill_selection: Dict[str, Any]
    skill: Dict[str, Any]
    report_template: str

    max_analysis_rounds: int
    analysis_round: int
    max_sql_attempts: int
    max_result_rows: Optional[int]

    chief_decision: Dict[str, Any]
    chief_decision_history: List[Dict[str, Any]]
    director_action: str
    analysis_goal: str

    current_query_id: str
    current_evidence_plan: Dict[str, Any]
    sql_attempts: int
    sql: str
    current_sql: str

    audit_passed: bool
    audit_message: str

    query_result: List[Dict[str, Any]]
    result_preview: List[Dict[str, Any]]
    result_columns: List[str]
    result_row_count: int
    result_path: str
    result_truncated: bool
    query_artifacts: List[Dict[str, Any]]

    current_processed_data: Dict[str, Any]
    current_data_issue: List[str]
    current_insight: Dict[str, Any]
    current_analysis_issue: List[str]
    current_analysis_round: Dict[str, Any]
    analysis_rounds: List[Dict[str, Any]]

    analysis_result: str
    report: str
    report_path: str
    metadata_path: str

    error: Optional[str]
