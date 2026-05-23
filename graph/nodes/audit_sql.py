"""SQL 审计节点。

这个文件定义 SQL 运行预检 ToolNode：不做字段或关键字审查，只检查 SQL 是否能运行，
以及查询结果是否至少返回一行。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pymysql

from graph.nodes.base import ToolNode


class AuditSQLNode(ToolNode):
    """通过只读事务运行 SQL，检查是否报错以及结果是否为空的工具节点。"""

    name = "audit_sql"
    title = "审计 SQL"
    description = "运行 SQL 预检，检查是否报错以及查询结果是否为空。"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """审计当前 SQL，并决定通过还是打回 SQL 工程师。

        输入:
            state: 当前图状态；需要包含 `sql` 和 `database`，可选包含 `sql_attempts` 与 `max_sql_attempts`。
        输出:
            包含 `audit_passed` 和 `audit_message` 的状态更新；未通过时由 workflow 路由回 SQL 工程师重写。
        """
        audit_result = self.audit(sql=state["sql"], conn=state.get("database"))
        if not audit_result["passed"]:
            max_attempts = int(state.get("max_sql_attempts") or 3)
            attempts = int(state.get("sql_attempts") or 0)
            if attempts >= max_attempts:
                raise ValueError(f"SQL 运行预检在 {attempts} 次尝试后仍未通过：{audit_result['message']}")
            return {
                "audit_passed": False,
                "audit_message": str(audit_result["message"]),
            }
        return {
            "audit_passed": True,
            "audit_message": str(audit_result["message"]),
        }

    def audit(self, sql: str, conn: Any = None) -> Dict[str, object]:
        """执行 SQL 运行预检。

        输入:
            sql: 待检查的 SQL 字符串。
            conn: 数据库连接配置对象。
        输出:
            包含 `passed` 布尔值和 `message` 文本的审计结果。
        """
        if not (sql or "").strip():
            return {"passed": False, "message": "SQL 为空。"}
        if conn is None:
            return {"passed": False, "message": "SQL 运行预检缺少数据库连接。"}
        return self.runtime_audit(sql, conn)

    def runtime_audit(self, sql: str, conn: Any) -> Dict[str, object]:
        """在只读事务中运行 SQL，并检查是否至少返回一行。

        输入:
            sql: 待预检的 SQL。
            conn: MySQL 连接配置对象。
        输出:
            包含 `passed` 布尔值和 `message` 文本的运行预检结果。
        """
        if conn.type != "mysql":
            return {"passed": False, "message": f"SQL 运行预检当前只支持 MySQL，暂不支持 {conn.type}。"}
        if not conn.database:
            return {"passed": False, "message": "MySQL 连接缺少 database 参数，无法运行 SQL 预检。"}

        db = None
        try:
            db = pymysql.connect(
                host=conn.host,
                port=int(conn.port),
                user=conn.user,
                password=conn.password,
                database=conn.database,
                charset="utf8mb4",
                connect_timeout=300,
                read_timeout=300,
                write_timeout=300,
                autocommit=False,
                cursorclass=pymysql.cursors.SSDictCursor,
            )
            with db.cursor() as cursor:
                cursor.execute("START TRANSACTION READ ONLY")
                cursor.execute(self.remove_tail_semicolon(sql))
                if cursor.description is None:
                    return {
                        "passed": False,
                        "message": "SQL 运行预检失败：语句没有返回查询结果集。",
                    }
                first_row = cursor.fetchone()
                if first_row is None:
                    return {
                        "passed": False,
                        "message": "SQL 运行预检失败：查询结果为 0 行。",
                    }
        except pymysql.MySQLError as exc:
            return {
                "passed": False,
                "message": f"SQL 运行预检失败：{exc}",
            }
        finally:
            if db:
                db.rollback()
                db.close()

        return {"passed": True, "message": "SQL 运行预检通过：SQL 可运行，且查询结果至少返回 1 行。"}

    def remove_tail_semicolon(self, sql: str) -> str:
        """去掉 SQL 末尾的分号。

        输入:
            sql: 原始 SQL 字符串。
        输出:
            末尾不带分号的 SQL 字符串。
        """
        return (sql or "").strip().removesuffix(";").strip()

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成任务步骤中展示的 SQL 审计摘要。

        输入:
            output: `run` 返回的状态更新。
        输出:
            人类可读的审计摘要。
        """
        return output.get("audit_message") or "SQL 运行预检通过。"
