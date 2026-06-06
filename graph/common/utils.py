"""graph 节点共用的小工具函数。

目前只放多个 Agent 都会用到的 JSON 序列化和模型输出解析逻辑。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Tuple


def json_dumps(value: Any) -> str:
    """把 Python 对象序列化成适合放进 prompt 或元数据的 JSON 字符串。

    输入:
        value: 任意可 JSON 化的 Python 对象；遇到非标准类型时会用 `str` 兜底。

    输出:
        保留中文字符、带缩进的 JSON 字符串。
    """
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def parse_json_object(text: str) -> Dict[str, Any]:
    """从模型输出中提取一个 JSON 对象。

    输入:
        text: 模型原始输出；可以是纯 JSON，也可以包在 Markdown JSON 代码块里，
            或者前后带有少量解释文字。

    输出:
        成功解析时返回 JSON 对象对应的 dict；失败时返回空 dict。
    """
    cleaned = (text or "").strip()
    code_match = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.IGNORECASE | re.DOTALL)
    if code_match:
        cleaned = code_match.group(1).strip()

    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            value = json.loads(cleaned[start : end + 1])
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def split_think_content(value: Any) -> Tuple[str, str]:
    """Split model output into visible body text and hidden thinking text."""
    source = str(value or "")
    open_tag = "<think>"
    close_tag = "</think>"
    body: list[str] = []
    thought: list[str] = []
    index = 0
    in_thought = False

    while index < len(source):
        if in_thought:
            close_index = source.find(close_tag, index)
            if close_index == -1:
                thought.append(source[index:])
                break
            thought.append(source[index:close_index])
            index = close_index + len(close_tag)
            in_thought = False
            continue

        open_index = source.find(open_tag, index)
        close_index = source.find(close_tag, index)

        if open_index == -1:
            if close_index == -1:
                body.append(source[index:])
                break
            body.append(source[index:close_index])
            index = close_index + len(close_tag)
            continue

        body.append(source[index:open_index])
        index = open_index + len(open_tag)
        in_thought = True

    return "".join(body).strip(), "".join(thought).strip()
