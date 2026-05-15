from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from schemas import DatabaseConnection, DatabaseServerConnection, TestConnectionResponse
from services.database_service import (
    delete_database_connection,
    discover_mysql_databases,
    list_available_database_connections,
    list_saved_database_connections,
    save_database_connection,
    test_saved_database_connection,
    test_mysql_connection,
)


router = APIRouter(prefix="/databases", tags=["databases"])


@router.get("/available_list")
def list_available_connections() -> Dict[str, Any]:
    """获取可用于创建分析任务的数据库连接列表。"""
    return {
        "success": True,
        "connections": list_available_database_connections(),
    }


@router.get("/saved_list")
def list_saved_connections() -> Dict[str, Any]:
    """获取数据库管理页的全部已保存连接。"""
    return {
        "success": True,
        "connections": list_saved_database_connections(),
    }


@router.post("/discover_databases")
def discover_databases(conn: DatabaseServerConnection) -> Dict[str, Any]:
    """根据服务器连接配置查询当前账号可见的数据库。"""
    if conn.type == "mysql":
        result = discover_mysql_databases(conn)
        return {
            "success": True,
            "message": "数据库列表获取成功",
            "database_type": conn.type,
            **result,
        }

    raise HTTPException(
        status_code=400,
        detail=f"当前后端 MVP 暂未实现 {conn.type} 的数据库列表查询，先请使用 MySQL。",
    )


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


@router.post("/{connection_id}/test")
def test_saved_connection(connection_id: str) -> Dict[str, Any]:
    """刷新一个已保存连接的可用状态。"""
    return test_saved_database_connection(connection_id)


@router.delete("/{connection_id}")
def delete_connection(connection_id: str) -> Dict[str, Any]:
    """删除一个已保存数据库连接。"""
    delete_database_connection(connection_id)
    return {
        "success": True,
        "message": "数据库连接已删除",
        "connection_id": connection_id,
    }


@router.post("/save")
def save_connection(conn: DatabaseConnection) -> Dict[str, Any]:
    """保存数据库连接配置。"""
    if conn.type == "mysql":
        test_result = test_mysql_connection(conn)
        if not test_result.success:
            raise HTTPException(status_code=400, detail=test_result.message)
    else:
        raise HTTPException(
            status_code=400,
            detail=f"当前后端 MVP 暂未实现 {conn.type} 的真实连接保存，先请使用 MySQL。",
        )

    connection = save_database_connection(conn)
    return {
        "success": True,
        "message": "数据库连接配置已保存",
        "connection": connection,
    }
