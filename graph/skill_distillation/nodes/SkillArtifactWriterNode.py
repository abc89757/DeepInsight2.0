"""Skill 文件撰写节点。"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

from graph.common.base import AgentNode
from graph.common.utils import json_dumps


class SkillArtifactWriterNode(AgentNode):
    """根据场景沉淀分析生成单个 Skill md 文件。"""

    name = "skill_artifact_writer"
    title = "Skill 文件撰写人"
    description = "根据沉淀分析生成当前 skill_type 对应的 Markdown 文件。"
    system_prompt = """
你是 Skill 文件撰写人。你负责把 Skill 场景分析师给出的沉淀方向，写成一个可以放入 Skill 文件夹的 Markdown 文件。

请用中文输出目标 Markdown 文件正文，不要输出 JSON，不要解释你如何写作。
文件内容要像长期可复用的 Skill 规则，而不是一次任务复盘。

写作原则：
1. 写可复用规则，不写本次任务的具体结论。
2. 可以使用本次任务作为启发，但要抽象成适用条件、判断规则、降级策略和注意事项。
3. 可以参考同类型 Skill 文件的结构和语气，但不要照抄。
4. 不要写具体任务 ID、文件路径、node_outputs、outputs、具体 SQL 结果路径。
5. 如果涉及具体字段名，只能作为“常见字段示例”，不能写成唯一要求。
""".strip()
    temperature = 0.25
    use_stream = True

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """生成 Markdown 文件内容。"""
        raw_output = self.call_llm(self.build_prompt(state), state)
        self.save_raw_llm_output(state, raw_output)
        markdown_content = self.clean_markdown(raw_output)
        if not markdown_content:
            raise ValueError("SkillArtifactWriterNode 没有返回有效 Markdown 内容。")

        return {
            "writer_message": raw_output,
            "markdown_content": markdown_content,
            "status": "running",
        }

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造 Skill 文件撰写 prompt。"""
        return f"""
当前正在生成的 Skill 文件类型：
{state.get("skill_type", "")}

目标文件名：
{state.get("file_name", "")}

本文件写作规格：
{json_dumps(state.get("artifact_spec", {}))}

本次 Skill 沉淀的统一场景方向：
{state.get("scene_direction", "")}

场景分析师给出的沉淀方向：
{state.get("scene_mining_message", "")}

用户问题与分析轮次上下文：
{json_dumps(state.get("context", {}))}

同类型参考 Skill 文件内容：
{state.get("reference_skill_content", "")}

请直接输出 {state.get("file_name", "")} 的 Markdown 正文。
""".strip()

    def clean_markdown(self, text: str) -> str:
        """去掉模型可能包上的 Markdown 代码块外壳。"""
        content = (text or "").strip()
        match = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return content

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成节点摘要。"""
        content = output.get("markdown_content", "")
        return content[:500] if content else "Skill 文件撰写完成。"
