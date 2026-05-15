from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel

from schemas import AnalysisTaskContext, DatabaseConnection
from system_db import (
    encrypt_password,
    get_system_db,
    json_dumps,
    json_loads,
    now_str,
    serialize_row,
)
from task_store import TASK_STORE


def model_to_dict(obj: BaseModel) -> Dict[str, Any]:
    """Convert a Pydantic model to a dict in both Pydantic v1 and v2."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    return obj.dict()


def mask_connection(conn: DatabaseConnection) -> Dict[str, Any]:
    """Return connection data without exposing the plaintext password."""
    data = model_to_dict(conn)
    data["password"] = "******" if conn.password else ""
    return data


def normalize_task_status(status: Optional[str], error: Optional[str] = None) -> str:
    """Normalize runtime status values into database status values."""
    if error:
        return "failed"

    if not status:
        return "pending"

    status = status.lower()

    if status in {"created"}:
        return "pending"

    if status in {"pending", "running", "failed", "cancelled", "succeeded"}:
        return status

    if status in {"finished", "finish", "completed", "complete", "success"}:
        return "succeeded"

    if status in {"error", "exception"}:
        return "failed"

    return status


def upsert_database_connection(conn: DatabaseConnection) -> str:
    """Save or update a database connection by alias."""
    conn_id = uuid4().hex
    password_encrypted = encrypt_password(conn.password or "")

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM database_connections WHERE alias = %s",
                (conn.alias,),
            )
            row = cursor.fetchone()

            if row:
                conn_id = row["id"]
                cursor.execute(
                    """
                    UPDATE database_connections
                    SET
                        db_type = %s,
                        host = %s,
                        port = %s,
                        username = %s,
                        password_encrypted = %s,
                        database_name = %s,
                        status = 'available',
                        last_test_time = NOW(),
                        last_error = NULL
                    WHERE id = %s
                    """,
                    (
                        conn.type,
                        conn.host,
                        conn.port,
                        conn.user,
                        password_encrypted,
                        conn.database,
                        conn_id,
                    ),
                )
                return conn_id

            cursor.execute(
                """
                INSERT INTO database_connections (
                    id, alias, db_type, host, port, username,
                    password_encrypted, database_name, status, last_test_time
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'available', NOW())
                """,
                (
                    conn_id,
                    conn.alias,
                    conn.type,
                    conn.host,
                    conn.port,
                    conn.user,
                    password_encrypted,
                    conn.database,
                ),
            )

    return conn_id


def insert_analysis_task(
    task_id: str,
    request: AnalysisTaskContext,
    connection_id: str,
    precheck_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Insert the task master record into analysis_tasks."""
    question = request.question.strip()
    title = question[:40] if len(question) <= 40 else question[:40] + "..."
    now = now_str()

    task = {
        "task_id": task_id,
        "id": task_id,
        "title": title,
        "status": "pending",
        "stage": "waiting",
        "current_stage": "waiting",
        "message": "分析任务已创建，等待后台流程执行。",
        "question": question,
        "database_alias": request.database_alias,
        "database": mask_connection(request.database),
        "database_precheck": {
            "server_info": precheck_result.get("server_info"),
            "table_count": precheck_result.get("table_count"),
            "tables": precheck_result.get("tables", [])[:20],
        },
        "scene": request.scene,
        "report_depth": request.report_depth,
        "created_at": now,
        "updated_at": now,
        "error": None,
        "sql": None,
        "result_preview": [],
        "result_row_count": 0,
        "analysis_result": None,
        "report": None,
        "report_path": None,
    }

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO analysis_tasks (
                    id, title, question, status, current_stage, message,
                    connection_id, db_alias_snapshot, db_type_snapshot, db_name_snapshot,
                    scene, report_depth, latest_state_json,
                    created_at, updated_at
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, CAST(%s AS JSON),
                    NOW(), NOW()
                )
                """,
                (
                    task_id,
                    title,
                    question,
                    "pending",
                    "waiting",
                    task["message"],
                    connection_id,
                    request.database.alias,
                    request.database.type,
                    request.database.database,
                    request.scene,
                    request.report_depth,
                    json_dumps(task),
                ),
            )

    return task


def _next_step_order(cursor: Any, task_id: str) -> int:
    cursor.execute(
        "SELECT COALESCE(MAX(step_order), 0) + 1 AS next_order FROM task_steps WHERE task_id = %s",
        (task_id,),
    )
    row = cursor.fetchone() or {}
    return int(row.get("next_order") or 1)


def insert_task_step(
    task_id: str,
    step_name: str,
    step_title: str,
    status: str,
    input_summary: Optional[str] = None,
    output_summary: Optional[str] = None,
    output_json: Any = None,
    error_message: Optional[str] = None,
) -> str:
    """Insert one real runtime step and return its id."""
    step_id = uuid4().hex

    with get_system_db() as db:
        with db.cursor() as cursor:
            step_order = _next_step_order(cursor, task_id)
            cursor.execute(
                """
                INSERT INTO task_steps (
                    id, task_id, step_order, step_name, step_title,
                    status, input_summary, output_summary, output_json,
                    error_message, started_at, finished_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, CAST(%s AS JSON),
                    %s,
                    CASE WHEN %s IN ('running', 'succeeded', 'failed') THEN NOW() ELSE NULL END,
                    CASE WHEN %s IN ('succeeded', 'failed', 'skipped') THEN NOW() ELSE NULL END
                )
                """,
                (
                    step_id,
                    task_id,
                    step_order,
                    step_name,
                    step_title,
                    status,
                    input_summary,
                    output_summary,
                    json_dumps(output_json) if output_json is not None else None,
                    error_message,
                    status,
                    status,
                ),
            )

    return step_id


def update_task_stage(
    task_id: str,
    stage: str,
    message: Optional[str],
    status: str = "running",
) -> None:
    """Update the task headline state when a node starts or the task ends."""
    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE analysis_tasks
                SET
                    status = %s,
                    current_stage = %s,
                    message = %s,
                    started_at = CASE
                        WHEN started_at IS NULL AND %s IN ('running', 'succeeded', 'failed')
                        THEN NOW()
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN finished_at IS NULL AND %s IN ('succeeded', 'failed', 'cancelled')
                        THEN NOW()
                        ELSE finished_at
                    END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    stage,
                    message,
                    status,
                    status,
                    task_id,
                ),
            )


def start_task_step(
    task_id: str,
    step_name: str,
    step_title: str,
    input_summary: Optional[str] = None,
    message: Optional[str] = None,
) -> str:
    """Record that a LangGraph node has started."""
    step_id = insert_task_step(
        task_id=task_id,
        step_name=step_name,
        step_title=step_title,
        status="running",
        input_summary=input_summary,
        output_summary=message,
    )
    update_task_stage(task_id, step_name, message or step_title, status="running")
    return step_id


def finish_task_step(
    step_id: str,
    output_summary: Optional[str] = None,
    output_json: Any = None,
) -> None:
    """Mark one task step as succeeded."""
    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE task_steps
                SET
                    status = 'succeeded',
                    output_summary = COALESCE(%s, output_summary),
                    output_json = COALESCE(CAST(%s AS JSON), output_json),
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    output_summary,
                    json_dumps(output_json) if output_json is not None else None,
                    step_id,
                ),
            )


def fail_task_step(step_id: str, error_message: str) -> None:
    """Mark one task step as failed."""
    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE task_steps
                SET
                    status = 'failed',
                    error_message = %s,
                    finished_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error_message, step_id),
            )


def insert_database_precheck_step(task_id: str, precheck_result: Dict[str, Any]) -> None:
    """Record the completed database precheck as a real task step."""
    table_count = precheck_result.get("table_count", 0)
    insert_task_step(
        task_id=task_id,
        step_name="database_precheck",
        step_title="数据库连接预检",
        status="succeeded",
        output_summary=f"数据库连接成功，检测到 {table_count} 张表。",
        output_json=precheck_result,
    )


def infer_columns_from_preview(rows: Any) -> list:
    """Infer column names from preview rows."""
    if not rows:
        return []

    first = rows[0]

    if isinstance(first, dict):
        return list(first.keys())

    if isinstance(first, (list, tuple)):
        return [f"col_{i + 1}" for i in range(len(first))]

    return ["value"]


def _local_file_info(uri: Optional[str]) -> Dict[str, Any]:
    if not uri:
        return {"file_name": None, "size_bytes": None}

    path = Path(uri)
    return {
        "file_name": path.name,
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def upsert_task_artifact(
    task_id: str,
    artifact_type: str,
    uri: Optional[str],
    mime_type: Optional[str],
    description: Optional[str],
    storage_type: str = "local",
) -> Optional[str]:
    """Register a generated file in task_artifacts and return the artifact id."""
    if not uri:
        return None

    file_info = _local_file_info(uri)

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT id FROM task_artifacts
                WHERE task_id = %s AND artifact_type = %s AND uri = %s
                LIMIT 1
                """,
                (task_id, artifact_type, uri),
            )
            existing = cursor.fetchone()

            if existing:
                artifact_id = existing["id"]
                cursor.execute(
                    """
                    UPDATE task_artifacts
                    SET
                        storage_type = %s,
                        file_name = %s,
                        mime_type = %s,
                        size_bytes = %s,
                        description = %s
                    WHERE id = %s
                    """,
                    (
                        storage_type,
                        file_info["file_name"],
                        mime_type,
                        file_info["size_bytes"],
                        description,
                        artifact_id,
                    ),
                )
                return artifact_id

            artifact_id = uuid4().hex
            cursor.execute(
                """
                INSERT INTO task_artifacts (
                    id, task_id, artifact_type, storage_type, uri,
                    file_name, mime_type, size_bytes, description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    artifact_id,
                    task_id,
                    artifact_type,
                    storage_type,
                    uri,
                    file_info["file_name"],
                    mime_type,
                    file_info["size_bytes"],
                    description,
                ),
            )
            return artifact_id


def upsert_query_result_from_state(task_id: str, state: Dict[str, Any]) -> None:
    """Sync SQL and query preview data into query_results."""
    sql = state.get("sql")
    rows = state.get("result_preview") or []
    row_count = state.get("result_row_count") or len(rows)
    result_artifact_id = upsert_task_artifact(
        task_id=task_id,
        artifact_type="result_csv",
        uri=state.get("result_path"),
        mime_type="text/csv",
        description="SQL 查询完整结果 CSV",
    )

    if not sql and not rows:
        return

    columns = infer_columns_from_preview(rows)
    preview_row_count = len(rows)

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM query_results WHERE task_id = %s LIMIT 1",
                (task_id,),
            )
            existing = cursor.fetchone()

            if existing:
                cursor.execute(
                    """
                    UPDATE query_results
                    SET
                        sql_text = %s,
                        columns_json = CAST(%s AS JSON),
                        preview_rows_json = CAST(%s AS JSON),
                        row_count = %s,
                        preview_row_count = %s,
                        result_format = 'csv',
                        artifact_id = COALESCE(%s, artifact_id)
                    WHERE id = %s
                    """,
                    (
                        sql or "",
                        json_dumps(columns),
                        json_dumps(rows),
                        row_count,
                        preview_row_count,
                        result_artifact_id,
                        existing["id"],
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO query_results (
                        id, task_id, sql_text, columns_json, preview_rows_json,
                        row_count, preview_row_count, result_format, artifact_id
                    )
                    VALUES (
                        %s, %s, %s, CAST(%s AS JSON), CAST(%s AS JSON),
                        %s, %s, 'csv', %s
                    )
                    """,
                    (
                        uuid4().hex,
                        task_id,
                        sql or "",
                        json_dumps(columns),
                        json_dumps(rows),
                        row_count,
                        preview_row_count,
                        result_artifact_id,
                    ),
                )


def upsert_report_from_state(task_id: str, state: Dict[str, Any]) -> None:
    """Sync the generated Markdown report into reports."""
    report = state.get("report")

    if not report:
        return

    question = state.get("question") or "分析报告"
    title = f"{question[:40]}分析报告"

    if isinstance(report, dict):
        markdown_content = (
            report.get("markdown")
            or report.get("markdown_content")
            or report.get("content")
            or json_dumps(report)
        )
        summary = report.get("summary")
    else:
        markdown_content = str(report)
        summary = None

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO reports (
                    id, task_id, title, summary, markdown_content, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    summary = VALUES(summary),
                    markdown_content = VALUES(markdown_content),
                    updated_at = NOW()
                """,
                (
                    uuid4().hex,
                    task_id,
                    title,
                    summary,
                    markdown_content,
                ),
            )


def upsert_artifacts_from_state(task_id: str, state: Dict[str, Any]) -> None:
    """Register generated local files in task_artifacts."""
    upsert_task_artifact(
        task_id=task_id,
        artifact_type="result_csv",
        uri=state.get("result_path"),
        mime_type="text/csv",
        description="SQL 查询完整结果 CSV",
    )
    upsert_task_artifact(
        task_id=task_id,
        artifact_type="report_md",
        uri=state.get("report_path"),
        mime_type="text/markdown",
        description="Markdown 分析报告",
    )
    upsert_task_artifact(
        task_id=task_id,
        artifact_type="metadata_json",
        uri=state.get("metadata_path"),
        mime_type="application/json",
        description="任务执行元数据",
    )


def sync_task_state_to_db(task_id: str, state: Dict[str, Any]) -> None:
    """Sync the in-memory runtime state into durable task tables."""
    if not state:
        return

    status = normalize_task_status(state.get("status"), state.get("error"))
    current_stage = state.get("stage") or state.get("current_stage") or "waiting"
    message = state.get("message")
    error_message = state.get("error")

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                UPDATE analysis_tasks
                SET
                    status = %s,
                    current_stage = %s,
                    message = %s,
                    latest_state_json = CAST(%s AS JSON),
                    error_message = %s,
                    started_at = CASE
                        WHEN started_at IS NULL AND %s IN ('running', 'succeeded', 'failed')
                        THEN NOW()
                        ELSE started_at
                    END,
                    finished_at = CASE
                        WHEN finished_at IS NULL AND %s IN ('succeeded', 'failed', 'cancelled')
                        THEN NOW()
                        ELSE finished_at
                    END,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    status,
                    current_stage,
                    message,
                    json_dumps(state),
                    error_message,
                    status,
                    status,
                    task_id,
                ),
            )

    upsert_query_result_from_state(task_id, state)
    upsert_report_from_state(task_id, state)
    upsert_artifacts_from_state(task_id, state)


def list_tasks_from_db(limit: int = 100) -> list:
    """Read the task list for the sidebar."""
    for task_id, state in list(TASK_STORE.items()):
        try:
            sync_task_state_to_db(task_id, state)
        except Exception:
            print(f"同步任务 {task_id} 到数据库失败：")
            traceback.print_exc()

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    question,
                    status,
                    current_stage,
                    message,
                    created_at,
                    updated_at
                FROM analysis_tasks
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()

    result = []
    for row in rows:
        item = serialize_row(row)
        item["task_id"] = item["id"]
        item["stage"] = item.get("current_stage")
        result.append(item)

    return result


def delete_task_from_db(task_id: str) -> None:
    """Delete one analysis task and its cascading database records."""
    TASK_STORE.pop(task_id, None)

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute("DELETE FROM analysis_tasks WHERE id = %s", (task_id,))
            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail="任务不存在")


def get_task_detail_from_db(task_id: str) -> Dict[str, Any]:
    """Read task detail and join task / steps / query_result / report / artifacts."""
    state = TASK_STORE.get(task_id)
    if state:
        sync_task_state_to_db(task_id, state)

    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    title,
                    question,
                    status,
                    current_stage,
                    message,
                    db_alias_snapshot,
                    db_type_snapshot,
                    db_name_snapshot,
                    scene,
                    report_depth,
                    latest_state_json,
                    error_message,
                    created_at,
                    started_at,
                    finished_at,
                    updated_at
                FROM analysis_tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            task = cursor.fetchone()

            if not task:
                raise HTTPException(status_code=404, detail="任务不存在")

            cursor.execute(
                """
                SELECT
                    id,
                    task_id,
                    step_order,
                    step_name,
                    step_title,
                    status,
                    input_summary,
                    output_summary,
                    output_json,
                    artifact_id,
                    error_message,
                    started_at,
                    finished_at,
                    updated_at
                FROM task_steps
                WHERE task_id = %s
                ORDER BY step_order ASC
                """,
                (task_id,),
            )
            steps = cursor.fetchall()

            cursor.execute(
                """
                SELECT
                    id,
                    task_id,
                    sql_text,
                    columns_json,
                    preview_rows_json,
                    row_count,
                    preview_row_count,
                    result_format,
                    artifact_id,
                    created_at
                FROM query_results
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            query_result = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    id,
                    task_id,
                    title,
                    summary,
                    markdown_content,
                    html_content,
                    created_at,
                    updated_at
                FROM reports
                WHERE task_id = %s
                LIMIT 1
                """,
                (task_id,),
            )
            report = cursor.fetchone()

            cursor.execute(
                """
                SELECT
                    id,
                    task_id,
                    artifact_type,
                    storage_type,
                    uri,
                    file_name,
                    mime_type,
                    size_bytes,
                    checksum,
                    description,
                    created_at
                FROM task_artifacts
                WHERE task_id = %s
                ORDER BY created_at ASC
                """,
                (task_id,),
            )
            artifacts = cursor.fetchall()

    task = serialize_row(task)
    task["task_id"] = task["id"]
    task["stage"] = task.get("current_stage")
    task["error"] = task.get("error_message")

    latest_state = json_loads(task.pop("latest_state_json", None)) or {}

    real_stage = (
        latest_state.get("stage")
        or latest_state.get("current_stage")
        or task.get("current_stage")
        or "waiting"
    )

    task["stage"] = real_stage
    task["current_stage"] = real_stage
    task["message"] = latest_state.get("message") or task.get("message")
    task["status"] = latest_state.get("status") or task.get("status")
    task["database"] = latest_state.get("database")
    task["database_precheck"] = latest_state.get("database_precheck")
    task["sql"] = latest_state.get("sql")
    task["result_preview"] = latest_state.get("result_preview", [])
    task["result_row_count"] = latest_state.get("result_row_count", 0)
    task["analysis_result"] = latest_state.get("analysis_result")
    task["report_path"] = latest_state.get("report_path")

    clean_steps = []
    for step in steps:
        step = serialize_row(step)
        step["output_json"] = json_loads(step.get("output_json"))
        clean_steps.append(step)

    if query_result:
        query_result = serialize_row(query_result)
        query_result["columns_json"] = json_loads(query_result.get("columns_json")) or []
        query_result["preview_rows_json"] = json_loads(query_result.get("preview_rows_json")) or []

    if report:
        report = serialize_row(report)

    clean_artifacts = [serialize_row(item) for item in artifacts]

    return {
        "success": True,
        "task": task,
        "steps": clean_steps,
        "query_result": query_result,
        "report": report,
        "artifacts": clean_artifacts,
    }
