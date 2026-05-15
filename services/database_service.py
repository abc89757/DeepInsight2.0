from __future__ import annotations

from typing import Any, Dict, List
from uuid import uuid4

import pymysql
from fastapi import HTTPException

from schemas import DatabaseConnection, TestConnectionResponse
from system_db import decrypt_password, encrypt_password, get_system_db, serialize_row


def test_mysql_connection(conn: DatabaseConnection) -> TestConnectionResponse:
    """测试 MySQL 连接是否可用。"""
    if not conn.database:
        raise HTTPException(status_code=400, detail="MySQL 连接需要填写数据库名")

    try:
        db = pymysql.connect(
            host=conn.host,
            port=int(conn.port),
            user=conn.user,
            password=conn.password,
            database=conn.database,
            charset="utf8mb4",
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            autocommit=True,
        )
        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT VERSION();")
                version_row = cursor.fetchone()
                server_info = str(version_row[0]) if version_row else None
        finally:
            db.close()

        return TestConnectionResponse(
            success=True,
            message=f"连接成功：{conn.alias}",
            database_type=conn.type,
            alias=conn.alias,
            server_info=server_info,
        )
    except pymysql.MySQLError as exc:
        return TestConnectionResponse(
            success=False,
            message=f"连接失败：{exc}",
            database_type=conn.type,
            alias=conn.alias,
            server_info=None,
        )


def precheck_mysql_for_task(conn: DatabaseConnection) -> Dict[str, Any]:
    """
    创建分析任务前的 MySQL 预检查。

    这里比“测试连接”更严格：不仅要能连上，还要求目标库中存在数据表。
    """
    if not conn.database:
        raise HTTPException(status_code=400, detail="MySQL 连接需要填写数据库名")

    try:
        db = pymysql.connect(
            host=conn.host,
            port=int(conn.port),
            user=conn.user,
            password=conn.password,
            database=conn.database,
            charset="utf8mb4",
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            autocommit=True,
        )

        try:
            with db.cursor() as cursor:
                cursor.execute("SELECT VERSION();")
                version_row = cursor.fetchone()
                server_info = str(version_row[0]) if version_row else None

                cursor.execute("SHOW TABLES;")
                table_rows = cursor.fetchall()
                tables = [row[0] for row in table_rows]

                if not tables:
                    raise HTTPException(
                        status_code=400,
                        detail="数据库连接成功，但当前数据库中没有任何数据表，无法创建分析任务。",
                    )

                return {
                    "server_info": server_info,
                    "table_count": len(tables),
                    "tables": tables,
                }

        finally:
            db.close()

    except HTTPException:
        raise
    except pymysql.MySQLError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"数据库预检查失败：{exc}",
        )


def precheck_database_for_task(conn: DatabaseConnection) -> Dict[str, Any]:
    """创建分析任务前的统一数据库预检查入口。"""
    if conn.type == "mysql":
        return precheck_mysql_for_task(conn)

    raise HTTPException(
        status_code=400,
        detail=f"当前创建分析任务暂时只支持 MySQL，暂未支持 {conn.type}。",
    )


def list_database_connections() -> List[Dict[str, Any]]:
    """返回前端下拉框需要的连接信息，不包含密码和主机账号等敏感字段。"""
    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    alias,
                    database_name
                FROM database_connections
                ORDER BY updated_at DESC, created_at DESC
                """
            )
            rows = cursor.fetchall()

    return [serialize_row(row) for row in rows]


def save_database_connection(conn: DatabaseConnection) -> Dict[str, Any]:
    """
    保存或更新数据库连接配置。

    以 alias 作为唯一标识，重复保存同名连接时更新原记录。
    """
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
                        status = 'unknown',
                        last_test_time = NULL,
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
            else:
                cursor.execute(
                    """
                    INSERT INTO database_connections (
                        id, alias, db_type, host, port, username,
                        password_encrypted, database_name, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'unknown')
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

    return {
        "id": conn_id,
        "alias": conn.alias,
        "database_name": conn.database,
    }


def get_database_connection_by_id(connection_id: str) -> DatabaseConnection:
    """从系统库读取完整数据库连接配置，并解密密码。"""
    with get_system_db() as db:
        with db.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    alias,
                    db_type,
                    host,
                    port,
                    username,
                    password_encrypted,
                    database_name
                FROM database_connections
                WHERE id = %s
                """,
                (connection_id,),
            )
            row = cursor.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="未找到指定的数据库连接")

    try:
        password = decrypt_password(row["password_encrypted"])
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据库连接密码解密失败：{exc}") from exc

    return DatabaseConnection(
        type=row["db_type"],
        alias=row["alias"],
        host=row["host"],
        port=row["port"],
        user=row["username"],
        password=password,
        database=row["database_name"],
    )
