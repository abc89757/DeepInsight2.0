"""分析任务后台执行器。

这个文件负责在 FastAPI 后台任务里运行 LangGraph，并把每个节点的进度同步到内存任务状态中。
"""

from __future__ import annotations

import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from services.node_output_store import NODE_OUTPUT_DIR
from services.task_cancellation import TaskCancelled, cleanup_task_cancel, register_task
from services.task_events import close_task_events, publish_task_event
from services.task_tool_registry import close_task_tool_clients


STATE_SNAPSHOT_FILENAME = "state.json"
SENSITIVE_KEYS = {"password", "password_encrypted", "api_key", "token", "secret"}


def _to_jsonable(value: Any) -> Any:
    """把 graph state 中的值转换成可以安全写入 JSON 的对象。

    输入:
        value: 任意 Python 对象，可能包含 Pydantic 模型、Path、datetime 或普通容器。
    输出:
        可被 json.dumps 序列化的对象；敏感字段会被脱敏。
    """
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                result[key_text] = "******" if item else ""
            else:
                result[key_text] = _to_jsonable(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def save_state_snapshot(
    task_id: str,
    state: Dict[str, Any],
    stage: str,
    status: str = "running",
    error: str | None = None,
) -> str:
    """把当前 graph state 保存为本地 JSON 快照。

    输入:
        task_id: 当前任务 ID，文件名会使用这个 ID。
        state: 当前 graph state。
        stage: 刚执行完成或正在记录的节点名。
        status: 当前任务状态。
        error: 可选错误信息。
    输出:
        写入后的 JSON 快照路径字符串。
    """
    task_output_dir = NODE_OUTPUT_DIR / task_id
    task_output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = task_output_dir / STATE_SNAPSHOT_FILENAME
    temp_path = snapshot_path.with_suffix(".json.tmp")
    payload = {
        "_snapshot": {
            "task_id": task_id,
            "stage": stage,
            "status": status,
            "error": error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "state": _to_jsonable(state),
    }
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(snapshot_path)
    return str(snapshot_path)


def update_task(task_store: Dict[str, Dict[str, Any]], task_id: str, **kwargs: Any) -> None:
    """更新内存中的单个分析任务状态。

    输入:
        task_store: 任务状态字典，key 是 task_id。
        task_id: 当前要更新的任务 ID。
        **kwargs: 要合并到任务状态里的字段。
    输出:
        无返回值，直接修改 task_store 中的任务对象。
    """
    task = task_store.get(task_id)
    if not task:
        return
    task.update(kwargs)
    task["updated_at"] = datetime.now().isoformat(timespec="seconds")


def run_analysis_task(task_id: str, request: Any, task_store: Dict[str, Dict[str, Any]]) -> None:
    """运行一次完整的数据分析任务。

    输入:
        task_id: 当前任务 ID。
        request: API 层传入的分析请求对象。
        task_store: 内存任务状态字典。
    输出:
        无返回值，执行过程中持续更新 task_store。
    """
    output_dir = Path("outputs") / task_id
    output_dir.mkdir(parents=True, exist_ok=True)
    final_state: Dict[str, Any] = {}
    register_task(task_id)

    try:
        update_task(
            task_store,
            task_id,
            status="running",
            stage="start",
            message="后台分析流程已启动。",
            error=None,
        )
        publish_task_event(
            task_id,
            "task_started",
            {
                "stage": "start",
                "message": "后台分析流程已启动。",
            },
        )

        from graph.workflow import build_workflow

        workflow = build_workflow()
        initial_state = {
            "task_id": task_id,
            "question": request.question.strip(),
            "database": request.database,
            "database_alias": request.database_alias,
            "output_dir": str(output_dir),
            "status": "running",
            "stage": "start",
            "message": "后台分析流程已启动。",
            "max_analysis_rounds": 1,
            "analysis_round": 0,
            "max_sql_attempts": 3,
            "max_data_request_attempts": 3,
            "data_request_attempts": 0,
            "max_result_rows": None,
            "agent_messages": [],
            "analysis_rounds": [],
            "query_artifacts": [],
        }

        final_state = dict(initial_state)
        save_state_snapshot(task_id, final_state, stage="start")

        for event in workflow.stream(initial_state):
            for node_name, node_update in event.items():
                print(f"[task {task_id}] completed node: {node_name}")
                print(f"node output: {node_update}\n\n")
                if not isinstance(node_update, dict):
                    continue

                final_state.update(node_update)
                stage_message = _stage_message(node_name)
                final_state.update(
                    {
                        "status": "running",
                        "stage": node_name,
                        "message": stage_message,
                    }
                )
                snapshot_path = save_state_snapshot(task_id, final_state, stage=node_name)
                update_task(
                    task_store,
                    task_id,
                    status="running",
                    stage=node_name,
                    message=stage_message,
                    sql=final_state.get("sql"),
                    result_preview=final_state.get("result_preview", []),
                    result_row_count=final_state.get("result_row_count", 0),
                    analysis_result=final_state.get("analysis_result"),
                    report=final_state.get("report"),
                    report_path=final_state.get("report_path"),
                    state_snapshot_path=snapshot_path,
                )

        final_state.update(
            {
                "status": "finished",
                "stage": "finished",
                "message": "分析任务执行完成。",
            }
        )
        snapshot_path = save_state_snapshot(task_id, final_state, stage="finished", status="finished")
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
            state_snapshot_path=snapshot_path,
            error=None,
                )
        publish_task_event(
            task_id,
            "task_finished",
            {
                "stage": "finished",
                "message": "分析任务执行完成。",
                "report_path": final_state.get("report_path"),
            },
        )

    except TaskCancelled as exc:
        print(f"[task {task_id}] cancelled: {exc}")
        final_state.update(
            {
                "task_id": task_id,
                "status": "cancelled",
                "stage": "cancelled",
                "message": "分析任务已取消。",
                "error": None,
            }
        )
        save_state_snapshot(
            task_id,
            final_state,
            stage="cancelled",
            status="cancelled",
        )
        update_task(
            task_store,
            task_id,
            status="cancelled",
            stage="cancelled",
            message="分析任务已取消。",
            error=None,
        )
        publish_task_event(
            task_id,
            "task_cancelled",
            {
                "stage": "cancelled",
                "message": "分析任务已取消。",
            },
        )

    except Exception as exc:
        traceback.print_exc()
        final_state.update(
            {
                "task_id": task_id,
                "status": "failed",
                "stage": "failed",
                "message": "分析任务执行失败。",
                "error": str(exc),
            }
        )
        snapshot_path = save_state_snapshot(
            task_id,
            final_state,
            stage="failed",
            status="failed",
            error=str(exc),
        )
        update_task(
            task_store,
            task_id,
            status="failed",
            stage="failed",
            message="分析任务执行失败。",
            error=str(exc),
            state_snapshot_path=snapshot_path,
        )
        publish_task_event(
            task_id,
            "task_failed",
            {
                "stage": "failed",
                "message": "分析任务执行失败。",
                "error": str(exc),
            },
        )
    finally:
        close_task_tool_clients(task_id)
        cleanup_task_cancel(task_id)
        close_task_events(task_id)


def _stage_message(stage: str) -> str:
    """把节点名转换为前端展示用的进度文案。

    输入:
        stage: 当前 LangGraph 节点名。
    输出:
        适合展示给用户的中文进度文本。
    """
    mapping = {
        "load_schema": "正在读取数据库 Schema...",
        "skill_advisor": "正在选择分析场景 Skill...",
        "skill_loader": "正在加载分析场景规则...",
        "chief_analyst": "首席分析师正在决定下一步分析目标...",
        "evidence_planner": "证据规划师正在规划本轮数据证据...",
        "data_processor": "数据处理师正在规划数据提取策略...",
        "sql_engineer": "SQL 工程师正在生成 SQL...",
        "audit_sql": "正在审计 SQL...",
        "execute_sql": "正在执行 SQL 并保存结果...",
        "insight_analyst": "洞察分析师正在沉淀本轮发现...",
        "report_writer": "正在根据分析结果生成报告...",
    }
    return mapping.get(stage, f"正在执行节点：{stage}")
