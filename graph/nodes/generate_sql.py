from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.nodes.base import AgentNode


class GenerateSQLNode(AgentNode):
    name = "generate_sql"
    title = "生成 SQL"
    description = "根据查询规划生成只读 SQL。"
    system_prompt = "你只输出可执行的 MySQL SELECT SQL，不输出解释。"
    temperature = 0.1

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        prompt = self.build_prompt(state)
        raw_sql = self.call_llm(prompt, state)
        sql = self.clean_sql(raw_sql)
        return {"sql": sql}

    def build_prompt(self, state: Dict[str, Any]) -> str:
        return f"""
你是一个严谨的 MySQL Text-to-SQL 助手。请根据用户问题、数据库 Schema、场景 Skill 和查询规划，生成一条可以执行的 MySQL 查询 SQL。

强制要求：
1. 只允许生成只读查询 SQL；
2. 不允许生成 INSERT、UPDATE、DELETE、DROP、ALTER、TRUNCATE、CREATE 等修改数据库的语句；
3. 尽量只使用 Schema 中真实存在的表和字段；
4. 如果用户需求是分析趋势、排名、分布，可以使用 GROUP BY / ORDER BY / LIMIT；
5. 如果结果可能很多，请加 LIMIT；
6. 只输出 SQL 本身，不要解释，不要 Markdown 代码块。

用户问题：
{state["question"]}

查询规划：
{state["query_plan"]}

数据库 Schema：
{state["schema_info"]}

场景 Skill：
{state["skill_content"]}

只返回 SQL：
""".strip()

    def call_llm(self, prompt: str, state: Dict[str, Any]) -> str:
        return self.llm_client.complete(
            prompt=prompt,
            system_prompt=self.system_prompt,
            temperature=self.temperature,
            tools=self.tools,
            stream=self.stream,
            timeout=self.timeout,
        )

    def clean_sql(self, raw_sql: str) -> str:
        text = raw_sql.strip()

        code_match = re.search(r"```(?:sql)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if code_match:
            text = code_match.group(1).strip()

        text = re.sub(r"^\s*(SQL|sql|查询SQL|生成SQL)\s*[:：]\s*", "", text).strip()

        if ";" in text:
            first, *_ = text.split(";")
            text = first.strip() + ";"

        if not text.endswith(";"):
            text += ";"
        return text

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        sql = output.get("sql") or ""
        return f"SQL 生成完成，长度 {len(sql)}。"
