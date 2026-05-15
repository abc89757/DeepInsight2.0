"""
DeepInsightWorkflow

功能说明：
组装第一版 LangGraph 工作流。
当前版本只走“有 Skill”的主路径。
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    AnalyzeDataNode,
    AuditSQLNode,
    ExecuteSQLNode,
    GenerateReportNode,
    GenerateSQLNode,
    LoadSchemaNode,
    LoadSkillNode,
    PlanQueryNode,
)
from graph.state import GraphState


def build_workflow():
    graph = StateGraph(GraphState)

    load_schema = LoadSchemaNode()
    load_skill = LoadSkillNode()
    plan_query = PlanQueryNode()
    generate_sql = GenerateSQLNode()
    audit_sql = AuditSQLNode()
    execute_sql = ExecuteSQLNode()
    analyze_data = AnalyzeDataNode()
    generate_report = GenerateReportNode()

    graph.add_node(load_schema.name, load_schema)
    graph.add_node(load_skill.name, load_skill)
    graph.add_node(plan_query.name, plan_query)
    graph.add_node(generate_sql.name, generate_sql)
    graph.add_node(audit_sql.name, audit_sql)
    graph.add_node(execute_sql.name, execute_sql)
    graph.add_node(analyze_data.name, analyze_data)
    graph.add_node(generate_report.name, generate_report)

    graph.add_edge(START, load_schema.name)
    graph.add_edge(load_schema.name, load_skill.name)
    graph.add_edge(load_skill.name, plan_query.name)
    graph.add_edge(plan_query.name, generate_sql.name)
    graph.add_edge(generate_sql.name, audit_sql.name)
    graph.add_edge(audit_sql.name, execute_sql.name)
    graph.add_edge(execute_sql.name, analyze_data.name)
    graph.add_edge(analyze_data.name, generate_report.name)
    graph.add_edge(generate_report.name, END)

    return graph.compile()
