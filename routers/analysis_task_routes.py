from __future__ import annotations

from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, HTTPException

from schemas import AnalysisTaskContext, CreateTaskRequest, TaskResponse
from services.database_service import get_database_connection_by_id, precheck_database_for_task
from services.task_execution import run_analysis_task_with_persistence
from services.task_persistence import (
    get_task_detail_from_db,
    insert_database_precheck_step,
    insert_analysis_task,
    list_tasks_from_db,
)
from task_store import TASK_STORE


router = APIRouter(prefix="/analyst_task", tags=["analyst_task"])


@router.post("/create_task", response_model=TaskResponse)
def create_analysis_task(
    request: CreateTaskRequest,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    """
    创建分析任务。

    前端只传 connection_id；后端负责读取连接配置、解密密码、预检查连接，再创建任务。
    """
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="分析需求不能为空")

    try:
        database = get_database_connection_by_id(request.connection_id)
        precheck_result = precheck_database_for_task(database)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=f"创建任务失败：{exc.detail}",
        ) from exc

    task_request = AnalysisTaskContext(
        question=question,
        connection_id=request.connection_id,
        database_alias=database.alias,
        database=database,
        scene=request.scene,
        report_depth=request.report_depth,
    )

    task_id = uuid4().hex

    task = insert_analysis_task(
        task_id=task_id,
        request=task_request,
        connection_id=request.connection_id,
        precheck_result=precheck_result,
    )

    insert_database_precheck_step(task_id, precheck_result)

    TASK_STORE[task_id] = task

    background_tasks.add_task(
        run_analysis_task_with_persistence,
        task_id=task_id,
        request=task_request,
    )

    return TaskResponse(
        success=True,
        message="分析任务创建成功",
        task_id=task_id,
        status=task["status"],
        stage=task["stage"],
        task=task,
    )


@router.get("/tasks_list")
def get_tasks() -> Dict[str, Any]:
    """获取左侧任务列表。"""
    tasks = list_tasks_from_db(limit=100)
    return {
        "success": True,
        "tasks": tasks,
    }


@router.get("/tasks_info/{task_id}")
def get_task(task_id: str) -> Dict[str, Any]:
    """查询任务详情。"""
    return get_task_detail_from_db(task_id)
