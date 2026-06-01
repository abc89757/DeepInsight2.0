"""DeepInsight LangGraph 工作流定义。

当前流程:
load_schema -> skill_advisor -> skill_loader -> chief_analyst
-> evidence_planner -> sql_engineer -> audit_sql -> execute_sql
-> data_processor -> insight_analyst -> chief_analyst
-> report_writer。
"""

from __future__ import annotations

from typing import Any, Dict

from langgraph.graph import END, START, StateGraph

from graph.nodes import (
    AuditSQLNode,
    ChiefAnalystNode,
    ChartGeneratorNode,
    DataProcessorNode,
    EvidencePlannerNode,
    ExecuteSQLNode,
    InsightAnalystNode,
    LoadSchemaNode,
    ReportWriterNode,
    SkillAdvisorNode,
    SkillLoaderNode,
    SQLEngineerNode,
)
from graph.state import GraphState


def route_after_chief_analyst(state: Dict[str, Any]) -> str:
    """根据首席分析师的决策选择下一步节点。

    输入:
        state: 当前图状态；需要包含 `director_action`。
    输出:
        下一个节点名：`report_writer` 或 `evidence_planner`。
    """
    if state.get("director_action") == "ready_for_report":
        return "chart_generator"
    return "evidence_planner"


def route_after_audit_sql(state: Dict[str, Any]) -> str:
    """根据 SQL 运行预检结果选择执行 SQL 或返回 SQL 工程师重写。

    输入:
        state: 当前图状态；需要包含 `audit_passed`。
    输出:
        下一个节点名：`execute_sql` 或 `sql_engineer`。
    """
    if state.get("audit_passed"):
        return "execute_sql"
    return "sql_engineer"


def route_after_data_processor(state: Dict[str, Any]) -> str:
    """Route after the data processor decides whether more data is needed."""
    action = state.get("processor_action")
    if action == "need_sql_data":
        return "sql_engineer"
    if action == "metrics_ready":
        return "insight_analyst"
    return "insight_analyst"


def build_workflow():
    """构建并编译数据分析 LangGraph。

    输入:
        无显式输入；节点配置在函数内部实例化。
    输出:
        已编译的 LangGraph workflow，可用于 stream/invoke。
    """
    graph = StateGraph(GraphState)

    load_schema = LoadSchemaNode()
    skill_advisor = SkillAdvisorNode()
    skill_loader = SkillLoaderNode()
    chief_analyst = ChiefAnalystNode()
    evidence_planner = EvidencePlannerNode()
    sql_engineer = SQLEngineerNode()
    audit_sql = AuditSQLNode()
    execute_sql = ExecuteSQLNode()
    data_processor = DataProcessorNode()
    insight_analyst = InsightAnalystNode()
    chart_generator = ChartGeneratorNode()
    report_writer = ReportWriterNode()

    graph.add_node(load_schema.name, load_schema)
    graph.add_node(skill_advisor.name, skill_advisor)
    graph.add_node(skill_loader.name, skill_loader)
    graph.add_node(chief_analyst.name, chief_analyst)
    graph.add_node(evidence_planner.name, evidence_planner)
    graph.add_node(sql_engineer.name, sql_engineer)
    graph.add_node(audit_sql.name, audit_sql)
    graph.add_node(execute_sql.name, execute_sql)
    graph.add_node(data_processor.name, data_processor)
    graph.add_node(insight_analyst.name, insight_analyst)
    graph.add_node(chart_generator.name, chart_generator)
    graph.add_node(report_writer.name, report_writer)

    graph.add_edge(START, load_schema.name)
    graph.add_edge(load_schema.name, skill_advisor.name)
    graph.add_edge(skill_advisor.name, skill_loader.name)
    graph.add_edge(skill_loader.name, chief_analyst.name)

    graph.add_conditional_edges(
        chief_analyst.name,
        route_after_chief_analyst,
        {
            evidence_planner.name: evidence_planner.name,
            chart_generator.name: chart_generator.name,
        },
    )

    graph.add_edge(evidence_planner.name, data_processor.name)
    graph.add_conditional_edges(
        data_processor.name,
        route_after_data_processor,
        {
            sql_engineer.name: sql_engineer.name,
            insight_analyst.name: insight_analyst.name,
        },
    )
    graph.add_edge(sql_engineer.name, audit_sql.name)
    graph.add_conditional_edges(
        audit_sql.name,
        route_after_audit_sql,
        {
            execute_sql.name: execute_sql.name,
            sql_engineer.name: sql_engineer.name,
        },
    )
    graph.add_edge(execute_sql.name, data_processor.name)
    graph.add_edge(insight_analyst.name, chief_analyst.name)
    graph.add_edge(chart_generator.name, report_writer.name)
    graph.add_edge(report_writer.name, END)

    return graph.compile()
