from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

from schemas import DatabaseConnection, TestConnectionResponse
from services.database_service import (
    list_database_connections,
    save_database_connection,
    test_mysql_connection,
)


router = APIRouter(prefix="/databases", tags=["databases"])


@router.get("/list")
def list_connections() -> Dict[str, Any]:
    """获取已保存的数据库连接列表，不返回密码。"""
    return {
        "success": True,
        "connections": list_database_connections(),
    }


@router.post("/test", response_model=TestConnectionResponse)
def test_database_connection(conn: DatabaseConnection) -> TestConnectionResponse:
    """测试数据库连接。当前真实支持 MySQL。"""
    if conn.type == "mysql":
        return test_mysql_connection(conn)

    return TestConnectionResponse(
        success=False,
        message=f"当前后端 MVP 暂未实现 {conn.type} 的真实连接测试，先请使用 MySQL。",
        database_type=conn.type,
        alias=conn.alias,
        server_info=None,
    )


@router.post("/save")
def save_connection(conn: DatabaseConnection) -> Dict[str, Any]:
    """保存数据库连接配置。"""
    connection = save_database_connection(conn)
    return {
        "success": True,
        "message": "数据库连接配置已保存",
        "connection": connection,
    }
