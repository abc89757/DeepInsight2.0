"""Schema 读取节点。

这个文件定义 LoadSchemaNode，用来读取 MySQL 数据库的表、字段、类型和注释，供后续 Agent 做取数规划。
"""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Optional

import pymysql

from graph.nodes.base import ToolNode


class LoadSchemaNode(ToolNode):
    """读取数据库结构并格式化为文本的工具节点。"""

    name = "load_schema"
    title = "读取数据库结构"
    description = "读取业务库表、字段、类型和注释。"
    sensitive_column_keywords = {
        "password",
        "passwd",
        "pwd",
        "token",
        "secret",
        "key",
        "phone",
        "mobile",
        "email",
        "idcard",
        "identity",
    }

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """读取当前数据库 Schema 并写入 state。

        输入:
            state: 当前图状态；需要包含 `database` 连接配置。
        输出:
            包含 `schema_info` 的状态更新。
        """
        schema_info = self.get_schema(state["database"])
        return {"schema_info": schema_info}

    def get_schema(
        self,
        conn: Any,
        max_tables: int = 30,
        max_columns_per_table: int = 80,
        sample_rows_per_table: int = 5,
    ) -> str:
        """从 MySQL information_schema 中读取数据库结构。

        输入:
            conn: 数据库连接配置对象。
            max_tables: 最多读取的表数量。
            max_columns_per_table: 每张表最多读取的字段数量。
        输出:
            格式化后的 Schema 文本。
        """
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
            connect_timeout=300,
            read_timeout=300,
            write_timeout=300,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

        try:
            tables = self._load_tables(db, conn.database, max_tables)
            table_names = [table["table_name"] for table in tables]
            columns = self._load_columns(db, conn.database, table_names, max_columns_per_table)
            sample_rows = self._load_sample_rows(db, table_names, columns, sample_rows_per_table)
        finally:
            db.close()

        return self._format_schema(conn.database, tables, columns, sample_rows)

    def _load_tables(self, db: Any, database_name: str, max_tables: int) -> List[Dict[str, Any]]:
        """读取数据库中的表清单。

        输入:
            db: 已建立的 MySQL 连接。
            database_name: 数据库名称。
            max_tables: 最多读取的表数量。
        输出:
            表信息字典列表，每项包含表名和表注释。
        """
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
        """读取指定表的字段清单。

        输入:
            db: 已建立的 MySQL 连接。
            database_name: 数据库名称。
            table_names: 需要读取字段的表名列表。
            max_columns_per_table: 每张表最多读取的字段数量。
        输出:
            以表名为 key、字段信息列表为 value 的字典。
        """
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

    def _load_sample_rows(
        self,
        db: Any,
        table_names: List[str],
        columns: Dict[str, List[Dict[str, Any]]],
        sample_rows_per_table: int,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """读取每张表的少量样例数据。

        输入:
            db: 已建立的 MySQL 连接。
            table_names: 需要读取样例的表名列表。
            columns: 字段信息字典。
            sample_rows_per_table: 每张表最多读取的样例行数。
        输出:
            以表名为 key、样例行列表为 value 的字典。
        """
        samples: Dict[str, List[Dict[str, Any]]] = {}
        for table_name in table_names:
            try:
                rows = self._load_approx_sample_rows(
                    db=db,
                    table_name=table_name,
                    table_columns=columns.get(table_name, []),
                    sample_rows_per_table=sample_rows_per_table,
                )
            except pymysql.MySQLError as exc:
                rows = [{"sample_error": f"读取样例数据失败：{exc}"}]
            samples[table_name] = rows
        return samples

    def _load_approx_sample_rows(
        self,
        db: Any,
        table_name: str,
        table_columns: List[Dict[str, Any]],
        sample_rows_per_table: int,
    ) -> List[Dict[str, Any]]:
        """读取一张表的近似随机样例数据。

        输入:
            db: 已建立的 MySQL 连接。
            table_name: 表名。
            table_columns: 当前表的字段信息列表。
            sample_rows_per_table: 最多读取的样例行数。
        输出:
            样例行列表；有数值主键/唯一键时近似随机，否则取前几行。
        """
        if sample_rows_per_table <= 0:
            return []

        key_column = self._find_numeric_key_column(table_columns)
        if key_column:
            rows = self._load_rows_by_random_key(db, table_name, key_column, sample_rows_per_table)
            if rows:
                return [self._sanitize_sample_row(row) for row in rows]

        return [self._sanitize_sample_row(row) for row in self._load_first_rows(db, table_name, sample_rows_per_table)]

    def _find_numeric_key_column(self, table_columns: List[Dict[str, Any]]) -> Optional[str]:
        """查找适合近似随机采样的单列数值主键或唯一键。

        输入:
            table_columns: 当前表的字段信息列表。
        输出:
            字段名；如果找不到则返回 None。
        """
        numeric_prefixes = ("tinyint", "smallint", "mediumint", "int", "bigint", "decimal", "numeric")
        for key_type in ("PRI", "UNI"):
            for column in table_columns:
                column_type = str(column.get("column_type") or "").lower()
                column_key = str(column.get("column_key") or "").upper()
                if column_key == key_type and column_type.startswith(numeric_prefixes):
                    return str(column["column_name"])
        return None

    def _load_rows_by_random_key(
        self,
        db: Any,
        table_name: str,
        key_column: str,
        sample_rows_per_table: int,
    ) -> List[Dict[str, Any]]:
        """按数值 key 做近似随机采样。

        输入:
            db: 已建立的 MySQL 连接。
            table_name: 表名。
            key_column: 数值主键或唯一键字段名。
            sample_rows_per_table: 最多读取的样例行数。
        输出:
            样例行列表。
        """
        table_sql = self._quote_identifier(table_name)
        key_sql = self._quote_identifier(key_column)
        with db.cursor() as cursor:
            cursor.execute(f"SELECT MIN({key_sql}) AS min_id, MAX({key_sql}) AS max_id FROM {table_sql};")
            bounds = cursor.fetchone() or {}
            min_id = bounds.get("min_id")
            max_id = bounds.get("max_id")
            if min_id is None or max_id is None:
                return []

            rows: List[Dict[str, Any]] = []
            seen_keys = set()
            attempts = max(sample_rows_per_table * 6, 12)
            for _ in range(attempts):
                if len(rows) >= sample_rows_per_table:
                    break
                random_id = random.randint(int(min_id), int(max_id))
                cursor.execute(
                    f"SELECT * FROM {table_sql} WHERE {key_sql} >= %s ORDER BY {key_sql} LIMIT 1;",
                    (random_id,),
                )
                row = cursor.fetchone()
                if not row:
                    continue
                row_key = row.get(key_column)
                if row_key in seen_keys:
                    continue
                seen_keys.add(row_key)
                rows.append(row)
            return rows

    def _load_first_rows(self, db: Any, table_name: str, sample_rows_per_table: int) -> List[Dict[str, Any]]:
        """读取表中的前几行作为样例。

        输入:
            db: 已建立的 MySQL 连接。
            table_name: 表名。
            sample_rows_per_table: 最多读取的样例行数。
        输出:
            样例行列表。
        """
        table_sql = self._quote_identifier(table_name)
        with db.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {table_sql} LIMIT %s;", (sample_rows_per_table,))
            return list(cursor.fetchall())

    def _sanitize_sample_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """清理样例行，避免过长文本和敏感字段进入 prompt。

        输入:
            row: 原始样例行。
        输出:
            清理后的样例行。
        """
        cleaned: Dict[str, Any] = {}
        for key, value in row.items():
            key_text = str(key)
            if self._is_sensitive_column(key_text):
                cleaned[key_text] = "******" if value else value
                continue
            if isinstance(value, str) and len(value) > 120:
                cleaned[key_text] = value[:120] + "..."
            else:
                cleaned[key_text] = value
        return cleaned

    def _is_sensitive_column(self, column_name: str) -> bool:
        """判断字段名是否疑似敏感字段。

        输入:
            column_name: 字段名。
        输出:
            如果疑似敏感则返回 True，否则返回 False。
        """
        lowered = column_name.lower()
        return any(keyword in lowered for keyword in self.sensitive_column_keywords)

    def _quote_identifier(self, identifier: str) -> str:
        """安全地引用 MySQL 标识符。

        输入:
            identifier: 表名或字段名。
        输出:
            使用反引号包裹的 MySQL 标识符。
        """
        return f"`{identifier.replace('`', '``')}`"

    def _format_schema(
        self,
        database_name: str,
        tables: List[Dict[str, Any]],
        columns: Dict[str, List[Dict[str, Any]]],
        sample_rows: Dict[str, List[Dict[str, Any]]],
    ) -> str:
        """把表和字段信息格式化为给 Agent 使用的 Schema 文本。

        输入:
            database_name: 数据库名称。
            tables: 表信息列表。
            columns: 字段信息字典。
        输出:
            可直接放入 prompt 的 Schema 文本。
        """
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
            samples = sample_rows.get(table_name, [])
            if samples:
                lines.append("  样例数据（最多 5 行；有数值主键时近似随机，否则取前 5 行）：")
                for index, row in enumerate(samples, start=1):
                    row_text = json.dumps(row, ensure_ascii=False, default=str)
                    lines.append(f"  {index}. {row_text}")
            lines.append("")

        return "\n".join(lines).strip()

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成任务步骤中展示的 Schema 读取摘要。

        输入:
            output: `run` 返回的状态更新。
        输出:
            人类可读的 Schema 读取摘要。
        """
        schema_info = output.get("schema_info") or ""
        return f"数据库结构读取完成，Schema 文本长度 {len(schema_info)}。"
