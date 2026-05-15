from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql

from graph.nodes.base import ToolNode


class ExecuteSQLNode(ToolNode):
    name = "execute_sql"
    title = "执行 SQL"
    description = "执行查询 SQL，保存 CSV，并生成前端预览数据。"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        return self.execute(
            conn=state["database"],
            sql=state["sql"],
            output_dir=state["output_dir"],
        )

    def execute(
        self,
        conn: Any,
        sql: str,
        output_dir: str,
        max_rows: int = 500,
        preview_rows: int = 50,
    ) -> Dict[str, Any]:
        if conn.type != "mysql":
            raise ValueError(f"当前 SQL 执行只支持 MySQL，暂不支持 {conn.type}")
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
            read_timeout=30,
            write_timeout=30,
            autocommit=True,
            cursorclass=pymysql.cursors.DictCursor,
        )

        try:
            with db.cursor() as cursor:
                cursor.execute(sql)
                rows = list(cursor.fetchmany(max_rows + 1))
                truncated = len(rows) > max_rows
                rows = rows[:max_rows]
        finally:
            db.close()

        columns = list(rows[0].keys()) if rows else []
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        result_path = output_path / "result.csv"
        self.write_csv(result_path, columns, rows)

        preview = rows[:preview_rows]
        return {
            "query_result": rows,
            "result_preview": preview,
            "result_columns": columns,
            "result_row_count": len(rows),
            "result_path": str(result_path),
            "result_truncated": truncated,
        }

    def write_csv(self, path: Path, columns: List[str], rows: List[Dict[str, Any]]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            if not columns:
                f.write("")
                return
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        row_count = output.get("result_row_count", 0)
        result_path = output.get("result_path")
        if result_path:
            return f"SQL 执行完成，返回 {row_count} 行，结果已保存。"
        return f"SQL 执行完成，返回 {row_count} 行。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "result_preview": output.get("result_preview", []),
            "result_columns": output.get("result_columns", []),
            "result_row_count": output.get("result_row_count", 0),
            "result_path": output.get("result_path"),
            "result_truncated": output.get("result_truncated", False),
        }
