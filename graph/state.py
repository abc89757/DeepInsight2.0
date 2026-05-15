"""
GraphState

功能说明：
定义 LangGraph 工作流中各个节点共享的状态字段。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class GraphState(TypedDict, total=False):
    task_id: str

    question: str
    database: Any
    database_alias: str
    scene: str
    report_depth: str
    output_dir: str

    schema_info: str
    skill_content: str
    report_template: str

    query_plan: str
    sql: str

    audit_passed: bool
    audit_message: str

    query_result: List[Dict[str, Any]]
    result_preview: List[Dict[str, Any]]
    result_columns: List[str]
    result_row_count: int
    result_path: str

    analysis_result: str
    report: str
    report_path: str
    metadata_path: str

    error: Optional[str]
