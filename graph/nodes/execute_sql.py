"""SQL 执行节点。

这个文件定义 SQL 执行 ToolNode：执行只读查询、把完整结果保存为 CSV artifact，并只把预览数据写回 state。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import pymysql

from graph.nodes.base import ToolNode


class ExecuteSQLNode(ToolNode):
    """执行 SQL 并保存查询结果的工具节点。"""

    name = "execute_sql"
    title = "执行 SQL"
    description = "执行查询 SQL，保存 CSV artifact，并生成前端预览数据。"

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行当前 SQL 并把结果元信息写回 state。

        输入:
            state: 当前图状态；需要包含 `database`、`sql`、`output_dir`，可选包含 `current_query_id` 和 `max_result_rows`。
        输出:
            包含结果预览、结果路径、行数、字段、artifact 历史等信息的状态更新。
        """
        query_id = state.get("current_query_id") or "result"
        result = self.execute(
            conn=state["database"],
            sql=state["sql"],
            output_dir=state["output_dir"],
            query_id=query_id,
            max_rows=state.get("max_result_rows"),
        )

        artifacts = list(state.get("query_artifacts", []))
        artifacts.append(
            {
                "query_id": query_id,
                "path": result.get("result_path"),
                "row_count": result.get("result_row_count", 0),
                "columns": result.get("result_columns", []),
                "truncated": result.get("result_truncated", False),
            }
        )
        result["query_artifacts"] = artifacts
        return result

    def execute(
        self,
        conn: Any,
        sql: str,
        output_dir: str,
        query_id: str = "result",
        max_rows: Optional[int] = None,
        preview_rows: int = 50,
        batch_size: int = 1000,
    ) -> Dict[str, Any]:
        """连接数据库、执行 SQL，并把结果流式写入 CSV。

        输入:
            conn: 数据库连接配置对象；当前只支持 MySQL。
            sql: 已通过审计的只读 SQL。
            output_dir: 当前任务的输出目录。
            query_id: 本轮查询 ID，用于生成结果文件名。
            max_rows: 可选的最大落盘行数；为 None 时不主动截断。
            preview_rows: 写回 state 的预览行数。
            batch_size: 数据库游标每批抓取的行数。
        输出:
            包含 `query_result`、`result_preview`、`result_columns`、`result_row_count`、
            `result_path` 和 `result_truncated` 的字典。
        """
        if conn.type != "mysql":
            raise ValueError(f"当前 SQL 执行只支持 MySQL，暂不支持 {conn.type}")
        if not conn.database:
            raise ValueError("MySQL 连接缺少 database 参数")

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        result_path = output_path / self.result_filename(query_id)

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
            cursorclass=pymysql.cursors.SSDictCursor,
        )

        preview: List[Dict[str, Any]] = []
        columns: List[str] = []
        row_count = 0
        truncated = False

        try:
            with db.cursor() as cursor:
                cursor.execute(sql)
                columns = [item[0] for item in (cursor.description or [])]
                with result_path.open("w", encoding="utf-8-sig", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=columns) if columns else None
                    if writer:
                        writer.writeheader()

                    while True:
                        rows = list(cursor.fetchmany(batch_size))
                        if not rows:
                            break
                        for row in rows:
                            if max_rows is not None and row_count >= max_rows:
                                truncated = True
                                break
                            row_count += 1
                            if writer:
                                writer.writerow(row)
                            if len(preview) < preview_rows:
                                preview.append(dict(row))
                        if truncated:
                            break
        finally:
            db.close()

        return {
            "query_result": preview,
            "result_preview": preview,
            "result_columns": columns,
            "result_row_count": row_count,
            "result_path": str(result_path),
            "result_truncated": truncated,
        }

    def result_filename(self, query_id: str) -> str:
        """根据查询 ID 生成安全的 CSV 文件名。

        输入:
            query_id: 本轮查询 ID。
        输出:
            可安全写入本地文件系统的 CSV 文件名。
        """
        safe_query_id = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in query_id)
        return "result.csv" if safe_query_id == "result" else f"{safe_query_id}_result.csv"

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成任务步骤中展示的 SQL 执行摘要。

        输入:
            output: `run` 返回的状态更新。
        输出:
            人类可读的执行摘要。
        """
        row_count = output.get("result_row_count", 0)
        result_path = output.get("result_path")
        if result_path:
            return f"SQL 执行完成，返回 {row_count} 行，结果已保存。"
        return f"SQL 执行完成，返回 {row_count} 行。"

    def step_output(self, output: Dict[str, Any]) -> Dict[str, Any]:
        """挑选适合持久化到任务步骤中的结果信息。

        输入:
            output: `run` 返回的状态更新。
        输出:
            包含预览、列、行数、文件路径和 artifact 历史的简短字典。
        """
        return {
            "result_preview": output.get("result_preview", []),
            "result_columns": output.get("result_columns", []),
            "result_row_count": output.get("result_row_count", 0),
            "result_path": output.get("result_path"),
            "result_truncated": output.get("result_truncated", False),
            "query_artifacts": output.get("query_artifacts", []),
        }
