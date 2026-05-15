from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from fastapi import APIRouter

from routers.analysis_task_routes import router as analysis_task_router
from routers.database_routes import router as database_router


router = APIRouter(prefix="/api")
router.include_router(database_router)
router.include_router(analysis_task_router)


@router.get("/health")
def health() -> Dict[str, Any]:
    """前端用来确认后端服务是否启动。"""
    return {
        "success": True,
        "message": "DeepInsight API is running",
        "time": datetime.now().isoformat(timespec="seconds"),
    }
