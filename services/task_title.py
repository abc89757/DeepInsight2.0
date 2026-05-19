from __future__ import annotations

import re

from services.llm_client import LLMClient


def generate_task_title(question: str) -> str:
    """Generate a short task title from the user's analysis request."""
    try:
        raw_title = LLMClient().complete(
            prompt=build_task_title_prompt(question),
            system_prompt="你只输出任务标题本身，不输出任何解释。",
            temperature=0.1,
            timeout=300,
        )
        title = clean_task_title(raw_title)
        if title:
            return title
    except Exception:
        pass

    return fallback_task_title(question)


def build_task_title_prompt(question: str) -> str:
    return f"""
你是一个数据分析任务标题生成器。
请根据用户的数据分析需求，生成一个简短中文任务标题。

规则：
1. 标题不超过 15 个汉字；
2. 只输出标题本身；
3. 不要输出解释；
4. 不要加引号；
5. 不要加“标题：”；
6. 不要使用句号、冒号、换行或 Markdown；
7. 标题要准确概括分析目标。

示例：
用户需求：
分析最近三个月各门店销售额变化，找出增长最快和下滑最明显的门店

输出：
门店销售趋势分析

用户需求：
{question}

输出：
""".strip()


def clean_task_title(raw_title: str) -> str:
    title = (raw_title or "").strip()
    if not title:
        return ""

    title = title.splitlines()[0].strip()
    title = re.sub(r"^\s*(标题|任务标题|输出)\s*[:：]\s*", "", title).strip()
    title = title.strip("「」《》“”\"'` ")
    return title


def fallback_task_title(question: str) -> str:
    title = question.strip()[:15]
    return title.rstrip("，。！？,.!?；;：: ") or "未命名分析任务"
