"""场景顾问节点。

这个文件定义 SkillAdvisorNode，用来根据用户问题从本地 Skill 列表中选择一个分析场景。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from graph.nodes.base import AgentNode
from graph.nodes.utils import json_dumps, parse_json_object


_METADATA_DELIMITER_RE = re.compile(r"^-{3,}\s*$")


def _read_first_existing(paths: List[Path]) -> str:
    """读取候选路径中第一个存在的 UTF-8 文本文件。

    输入:
        paths: 按优先级排序的候选文件路径列表。

    输出:
        第一个存在文件的文本内容；如果都不存在，返回空字符串。
    """
    for path in paths:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def _parse_skill_metadata(profile: str) -> Dict[str, str]:
    """解析 SKILL.md 开头分割线包裹的元数据块。

    输入:
        profile: Skill 文件全文；预期以 `---` 或更长横线开头，第二个横线结束元数据块。

    输出:
        元数据字典；当前主要关注 `name` 和 `description`。
    """
    lines = profile.splitlines()
    start_index = next((idx for idx, line in enumerate(lines) if line.strip()), None)
    if start_index is None or not _METADATA_DELIMITER_RE.match(lines[start_index].strip()):
        return {}

    metadata_lines: List[str] = []
    for line in lines[start_index + 1 :]:
        if _METADATA_DELIMITER_RE.match(line.strip()):
            break
        metadata_lines.append(line)
    else:
        return {}

    metadata: Dict[str, str] = {}
    for line in metadata_lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        if key in {"name", "description"}:
            metadata[key] = value.strip()
    return metadata


class SkillAdvisorNode(AgentNode):
    """负责为当前分析任务选择最合适 Skill 的 AgentNode。"""

    name = "skill_advisor"
    title = "场景顾问"
    description = "根据用户问题选择最合适的分析 Skill。"
    system_prompt = """
你是数据分析场景顾问。你负责根据用户的数据分析需求，从可用 Skill 中选择一个最合适的场景。

要求：
1. 只输出 JSON，不要输出 Markdown 或解释。
2. JSON 字符串内部如果需要引用字段值、标签或原文，请使用单引号或中文引号，不要使用英文双引号；如果必须使用英文双引号，必须写成转义形式 `\"`。

只输出 JSON：
{
  "skill_name": "skill folder name",
  "reason": "选择原因"
}
""".strip()
    temperature = 0.1
    use_stream = False
    skills_root = Path("skills")

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """执行 Skill 选择，并把选择结果写入 graph state。

        输入:
            state: 当前图状态；需要包含 `question`。

        输出:
            包含 `available_skills`、`selected_skill_name` 和 `skill_selection` 的状态更新。
        """
        # 获取可用 Skill
        available_skills = self.list_available_skills()
        prompt_state = {**state, "available_skills": available_skills}
        raw_output = self.call_llm(self.build_prompt(prompt_state), state)
        self.save_raw_llm_output(state, raw_output)
        response = parse_json_object(raw_output)

        # 如果LLM输出有误，就用兜底
        candidate = str(response.get("skill_name") or "general").strip()
        # 如果选择的Skill不存在，则返回通用场景,这是为了防止输出错误的skill名字
        skill_names = {item["name"] for item in available_skills}
        if candidate not in skill_names:
            candidate = "general" if "general" in skill_names else next(iter(skill_names), "general")

        selection = {
            "skill_name": candidate,
            "reason": response.get("reason") or "使用默认场景规则。",
        }
        return {
            "available_skills": available_skills,
            "selected_skill_name": candidate,
            "skill_selection": selection,
        }

    def list_available_skills(self) -> List[Dict[str, Any]]:
        """列出本地可用 Skill 文件夹及其简短描述。

        输入:
            无。

        输出:
            Skill 元数据列表，每项包含 `name` 和 `description`。
        """
        skills: List[Dict[str, Any]] = []
        # 如果没有skills的文件夹，则返回通用场景
        if not self.skills_root.exists():
            return [{"name": "general", "description": "通用数据分析场景。"}]

        # 遍历所有子目录
        for child in sorted(self.skills_root.iterdir()):
            if not child.is_dir():
                continue
            # 读取 skill.md
            profile = _read_first_existing([child / "skill.md", child / "SKILL.md"])
            # 截取开头那一段，并解析成字典返回
            metadata = _parse_skill_metadata(profile)
            description = metadata.get("description")
            # 兜底策略，如果没有描述，则截取 skill.md 的开头
            if not description:
                description = " ".join(profile.split())[:600] if profile else f"{child.name} analysis skill"
            skill_info = {"name": child.name, "description": description}
            if metadata.get("name"):
                skill_info["display_name"] = metadata["name"]
            skills.append(skill_info)

        return skills or [{"name": "general", "description": "通用数据分析场景。"}]

    def build_prompt(self, state: Dict[str, Any]) -> str:
        """构造 Skill 选择 prompt。

        输入:
            state: 当前图状态，额外包含 `available_skills`。

        输出:
            要求模型返回 JSON Skill 选择结果的 prompt 字符串。
        """
        return f"""
用户问题：
{state["question"]}

可用 Skill：
{json_dumps(state.get("available_skills", []))}
""".strip()

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """生成用于任务步骤日志的简短摘要。

        输入:
            output: `run` 返回的状态更新。

        输出:
            人类可读的简短摘要。
        """
        return f"当前分析场景确定为：{output.get('selected_skill_name')}"
