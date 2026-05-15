from __future__ import annotations

from typing import Any, Dict, List, Optional

import pymysql

from graph.nodes.base import ToolNode


class LoadSchemaNode(ToolNode):
    name = "load_schema"
    title = "读取数据库结构"
    description = "读取业务库表、字段、类型和注释。"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        schema_info = self.get_schema(state["database"])
        return {"schema_info": schema_info}

    def get_schema(self, conn: Any, max_tables: int = 30, max_columns_per_table: int = 80) -> str:
        if conn.type != "mysql":
            raise ValueError(f"当前 Schema 读取只支持 MySQL，暂不支持 {conn.type}")
        if not conn.database:
            raise ValueError("MySQL 连接缺少 database 参数")

        db = pymysql.connect(
            host=conn.host,
            port=int(conn.port),
            user=conn.user,
            password=conn.password,
            database=conn.database,
            charset="utf8mb4",
            connect_timeout=5,
            read_timeout=10,
            write_timeout=10,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

        try:
            tables = self._load_tables(db, conn.database, max_tables)
            table_names = [table["table_name"] for table in tables]
            columns = self._load_columns(db, conn.database, table_names, max_columns_per_table)
        finally:
            db.close()

        return self._format_schema(conn.database, tables, columns)

    def _load_tables(self, db: Any, database_name: str, max_tables: int) -> List[Dict[str, Any]]:
        sql = """
        SELECT TABLE_NAME AS table_name, TABLE_COMMENT AS table_comment
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = %s
        ORDER BY TABLE_NAME
        LIMIT %s;
        """
        with db.cursor() as cursor:
            cursor.execute(sql, (database_name, max_tables))
            return list(cursor.fetchall())

    def _load_columns(
        self,
        db: Any,
        database_name: str,
        table_names: List[str],
        max_columns_per_table: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        if not table_names:
            return result

        sql = """
        SELECT
            TABLE_NAME AS table_name,
            COLUMN_NAME AS column_name,
            COLUMN_TYPE AS column_type,
            IS_NULLABLE AS is_nullable,
            COLUMN_KEY AS column_key,
            COLUMN_COMMENT AS column_comment
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        LIMIT %s;
        """
        with db.cursor() as cursor:
            for table_name in table_names:
                cursor.execute(sql, (database_name, table_name, max_columns_per_table))
                result[table_name] = list(cursor.fetchall())
        return result

    def _format_schema(
        self,
        database_name: str,
        tables: List[Dict[str, Any]],
        columns: Dict[str, List[Dict[str, Any]]],
    ) -> str:
        lines = [f"数据库名：{database_name}", "", "数据库表结构："]
        for table in tables:
            table_name = table["table_name"]
            table_comment = table.get("table_comment") or ""
            title = f"表：{table_name}"
            if table_comment:
                title += f"  # {table_comment}"
            lines.append(title)

            for col in columns.get(table_name, []):
                key = f", key={col['column_key']}" if col.get("column_key") else ""
                comment = f", comment={col['column_comment']}" if col.get("column_comment") else ""
                lines.append(
                    f"  - {col['column_name']} ({col['column_type']}, nullable={col['is_nullable']}{key}{comment})"
                )
            lines.append("")

        return "\n".join(lines).strip()

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        schema_info = output.get("schema_info") or ""
        return f"数据库结构读取完成，Schema 文本长度 {len(schema_info)}。"
