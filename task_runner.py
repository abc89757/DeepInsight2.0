"""
AnalysisTaskRunner

功能说明：
1. 接收 FastAPI 创建的分析任务；
2. 调用 LangGraph 工作流执行 Text2SQL、SQL 审计、SQL 执行、数据分析和报告生成；
3. 将执行过程状态与最终结果写回 TASK_STORE，供前端轮询查看。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from graph.workflow import build_workflow


def update_task(task_store: Dict[str, Dict[str, Any]], task_id: str, **kwargs: Any) -> None:
    """更新内存任务状态。"""
    task = task_store.get(task_id)
    if not task:
        return
    task.update(kwargs)
    task["updated_at"] = datetime.now().isoformat(timespec="seconds")


def run_analysis_task(task_id: str, request: Any, task_store: Dict[str, Dict[str, Any]]) -> None:
    """后台执行完整分析任务。"""
    output_dir = Path("outputs") / task_id
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # 更新当前任务状态
        update_task(
            task_store,
            task_id,
            status="running",
            stage="start",
            message="后台分析流程已启动。",
            error=None,
        )

        # 构建工作流并执行
        workflow = build_workflow()
        # 构造初始化State，LangGraph的各个节点是通过一个共享的State传递信息的
        initial_state = {
            "task_id": task_id,
            "question": request.question.strip(),
            "database": request.database,
            "database_alias": request.database_alias,
            "scene": request.scene,
            "report_depth": request.report_depth,
            "output_dir": str(output_dir),
        }

        final_state: Dict[str, Any] = dict(initial_state)

        # stream 可以拿到每个节点的输出，方便前端看到阶段变化。
        # event是某个节点的输出
        for event in workflow.stream(initial_state):
            for node_name, node_update in event.items():
                print(f"[任务 {task_id}] 当前完成节点：{node_name}")
                print(f"任务结果为：{node_update}\n\n")
                # todo:为什么不是字典就跳过？那也会出问题啊，应该打回重做
                if not isinstance(node_update, dict):
                    continue

                # 把节点输出更新到全局状态中
                final_state.update(node_update)
                update_task(
                    task_store,
                    task_id,
                    status="running",
                    stage=node_name,
                    message=_stage_message(node_name),
                    sql=final_state.get("sql"),
                    result_preview=final_state.get("result_preview", []),
                    result_row_count=final_state.get("result_row_count", 0),
                    analysis_result=final_state.get("analysis_result"),
                    report=final_state.get("report"),
                    report_path=final_state.get("report_path"),
                )

        update_task(
            task_store,
            task_id,
            status="finished",
            stage="finished",
            message="分析任务执行完成。",
            sql=final_state.get("sql"),
            result_preview=final_state.get("result_preview", []),
            result_row_count=final_state.get("result_row_count", 0),
            result_path=final_state.get("result_path"),
            analysis_result=final_state.get("analysis_result"),
            report=final_state.get("report"),
            report_path=final_state.get("report_path"),
            metadata_path=final_state.get("metadata_path"),
            error=None,
        )

    except Exception as exc:
        update_task(
            task_store,
            task_id,
            status="failed",
            stage="failed",
            message="分析任务执行失败。",
            error=str(exc),
        )


def _stage_message(stage: str) -> str:
    """把节点名转成前端可展示的中文状态。"""
    mapping = {
        "load_schema": "正在读取数据库 Schema...",
        "load_skill": "正在加载业务场景规则...",
        "plan_query": "正在规划查询任务...",
        "generate_sql": "正在生成 SQL...",
        "audit_sql": "正在审计 SQL...",
        "execute_sql": "正在执行 SQL 并保存结果...",
        "analyze_data": "正在分析查询结果...",
        "generate_report": "正在生成分析报告...",
    }
    return mapping.get(stage, f"正在执行节点：{stage}")
