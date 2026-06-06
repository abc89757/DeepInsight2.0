"""场景定性 graph 的上下文构造工具。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from graph.skill_distillation.context import load_analysis_state


SKILLS_ROOT = Path("skills")


SCENE_DIRECTION_ROUND_FIELDS = [
    "round",
    "analysis_goal",
    "evidence_plan",
    "analysis_result",
    # "data_issue",
    # "analysis_issue",
]


def build_scene_direction_context(analysis_state: Dict[str, Any]) -> Dict[str, Any]:
    """从分析任务 state 中提取场景定性需要的上下文。"""
    rounds: list[Dict[str, Any]] = []
    for item in analysis_state.get("analysis_rounds", []) or []:
        if not isinstance(item, dict):
            continue
        rounds.append({field: item.get(field) for field in SCENE_DIRECTION_ROUND_FIELDS if field in item})

    return {
        "question": analysis_state.get("question", ""),
        "analysis_rounds": rounds,
    }


def load_existing_skill_summaries(skills_root: Path = SKILLS_ROOT) -> str:
    """读取所有已有 Skill 的 name/description 摘要。"""
    if not skills_root.exists():
        return ""

    summaries: list[str] = []
    for skill_dir in sorted(path for path in skills_root.iterdir() if path.is_dir()):
        skill_file = skill_dir / "SKILL.md"
        if not skill_file.exists():
            continue
        metadata = extract_skill_metadata(skill_file.read_text(encoding="utf-8"))
        name = metadata.get("name", "").strip()
        description = metadata.get("description", "").strip()
        if not name and not description:
            continue
        summaries.append(
            "\n".join(
                [
                    f"skill_id: {skill_dir.name}",
                    f"name: {name or skill_dir.name}",
                    f"description: {description}",
                ]
            ).strip()
        )

    return "\n\n".join(summaries)


def extract_skill_metadata(content: str) -> Dict[str, str]:
    """从 SKILL.md 开头 frontmatter 中提取 name 和 description。"""
    text = content or ""
    match = re.match(r"\s*---\s*\n(.*?)\n---", text, flags=re.DOTALL)
    if not match:
        return {}

    metadata: Dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        if key not in {"name", "description"}:
            continue
        metadata[key] = value.strip()
    return metadata


def build_scene_direction_initial_state(
    source_analysis_task_id: str,
    distillation_task_id: str,
    *,
    scene_direction_task_id: str | None = None,
    max_debate_rounds: int = 3,
    reference_skill_name: str = "product_sales",
) -> Dict[str, Any]:
    """构造场景定性 graph 初始 state。"""
    resolved_task_id = scene_direction_task_id or uuid4().hex
    resolved_max_rounds = max(1, min(int(max_debate_rounds or 3), 10))
    analysis_state = load_analysis_state(source_analysis_task_id)
    return {
        "task_id": resolved_task_id,
        "scene_direction_task_id": resolved_task_id,
        "distillation_task_id": distillation_task_id,
        "source_analysis_task_id": source_analysis_task_id,
        "context": build_scene_direction_context(analysis_state),
        "reference_skill_content": load_existing_skill_summaries(),
        "debate_round": 1,
        "max_debate_rounds": resolved_max_rounds,
        "status": "running",
    }
