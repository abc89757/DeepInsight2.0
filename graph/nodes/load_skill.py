from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from graph.nodes.base import ToolNode


class LoadSkillNode(ToolNode):
    name = "load_skill"
    title = "加载业务场景规则"
    description = "读取当前场景的 Skill 和报告模板。"
    skills_root = Path("skills")

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        skill_data = self.load_skill(state["scene"])
        return {
            "skill_content": skill_data["skill_content"],
            "report_template": skill_data["report_template"],
        }

    def load_skill(self, scene: str) -> Dict[str, str]:
        scene_name = (scene or "general").strip()
        skill_dir = self.skills_root / scene_name

        if not skill_dir.exists():
            skill_dir = self.skills_root / "general"

        skill_file = skill_dir / "SKILL.md"
        report_template_file = skill_dir / "report_template.md"

        if not skill_file.exists():
            raise FileNotFoundError(f"未找到 Skill 文件：{skill_file}")

        skill_content = skill_file.read_text(encoding="utf-8")
        report_template = ""
        if report_template_file.exists():
            report_template = report_template_file.read_text(encoding="utf-8")

        return {
            "skill_content": skill_content,
            "report_template": report_template,
        }

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        skill_length = len(output.get("skill_content") or "")
        template_length = len(output.get("report_template") or "")
        return f"业务场景规则加载完成，Skill {skill_length} 字，模板 {template_length} 字。"
