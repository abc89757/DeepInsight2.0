"""Skill 加载节点。

这个文件定义 SkillLoaderNode，用来按照已选择的 skill 名称读取本地分文件 Skill 内容。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from graph.nodes.base import ToolNode


def _read_first_existing(paths: List[Path]) -> str:
    """读取候选路径中第一个存在的 UTF-8 文本文件。

    输入:
        paths: 按优先级排序的候选文件路径。
    输出:
        第一个存在文件的文本内容；如果都不存在，返回空字符串。
    """
    for path in paths:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


class SkillLoaderNode(ToolNode):
    """根据已选 Skill 名称读取分文件规则的工具节点。"""

    name = "skill_loader"
    title = "加载 Skill"
    description = "根据已选择的 Skill 名称读取场景、指标/特征、计算、分析和报告规则。"
    skills_root = Path("skills")

    def run(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """读取当前 Skill，并写入结构化 skill 对象。

        输入:
            state: 当前图状态；需要包含 `selected_skill_name`，如果缺失则使用 general。
        输出:
            包含 `selected_skill_name`、`skill` 和 `report_template` 的状态更新。
        """
        skill_name = str(state.get("selected_skill_name") or "general").strip() or "general"
        skill_dir = self.skills_root / skill_name
        if not skill_dir.exists():
            skill_name = "general"
            skill_dir = self.skills_root / skill_name

        overview = _read_first_existing([skill_dir / "skill.md", skill_dir / "SKILL.md"])
        metrics = _read_first_existing([skill_dir / "metrics.md", skill_dir / "指标种类.md"]) or overview
        calculations = _read_first_existing([skill_dir / "calculations.md", skill_dir / "计算指标.md"]) or overview
        analysis = _read_first_existing([skill_dir / "analysis.md", skill_dir / "分析指标.md"]) or overview
        report_template = _read_first_existing(
            [skill_dir / "report_template.md", skill_dir / "报告模板.md"]
        )

        if not overview:
            raise FileNotFoundError(f"未找到 Skill 场景说明文件：{skill_dir / 'skill.md'}")

        skill = {
            "name": skill_name,
            "overview": overview,
            "metrics": metrics,
            "calculations": calculations,
            "analysis": analysis,
            "report_template": report_template,
        }
        return {
            "selected_skill_name": skill_name,
            "skill": skill,
            "report_template": report_template,
        }

    def summarize_output(self, output: Dict[str, Any]) -> Optional[str]:
        """返回任务步骤中展示的 Skill 加载摘要。

        输入:
            output: `run` 返回的状态更新。
        输出:
            人类可读的 Skill 加载摘要。
        """
        skill = output.get("skill") or {}
        return f"已加载 Skill：{skill.get('name', 'unknown')}"


class LoadSkillNode(SkillLoaderNode):
    """兼容旧代码的别名；新工作流使用 SkillLoaderNode。

    输入:
        与 SkillLoaderNode 相同。
    输出:
        与 SkillLoaderNode 相同。
    """

    name = "load_skill"
