"""Skill 沉淀上下文构造工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable
from uuid import uuid4


NODE_OUTPUT_DIR = Path("node_outputs")
SKILLS_ROOT = Path("skills")

SKILL_TYPE_FILE_NAMES = {
    "SKILL": "SKILL.md",
    "metrics": "metrics.md",
    "calculations": "calculations.md",
    "analysis": "analysis.md",
    "report_template": "report_template.md",
}

# ROUND_FIELDS_BY_SKILL_TYPE = {
#     "SKILL": ["round", "analysis_goal", "analysis_result", "data_issue", "analysis_issue"],
#     "metrics": ["round", "analysis_goal", "evidence_plan", "evidence_result", "data_issue"],
#     "calculations": ["round", "evidence_plan", "evidence_result", "data_issue"],
#     "analysis": ["round", "analysis_goal", "analysis_result", "data_issue", "analysis_issue"],
#     "report_template": ["round", "analysis_goal", "analysis_result", "data_issue", "analysis_issue"],
# }

# 先来一版保守点的
ROUND_FIELDS_BY_SKILL_TYPE = {
    "SKILL": ["round", "analysis_goal"],
    "metrics": ["round", "analysis_goal", "evidence_plan"],
    "calculations": ["round", "evidence_result", "data_issue"],
    "analysis": ["round", "evidence_result", "analysis_result", "data_issue", "analysis_issue"],
    "report_template": ["round", "analysis_goal", "analysis_result", "data_issue", "analysis_issue"],
}


def normalize_skill_type(skill_type: str) -> str:
    """规范化 Skill 文件类型。"""
    value = (skill_type or "").strip()
    if value.lower() == "skill":
        return "SKILL"
    return value


def skill_file_name(skill_type: str) -> str:
    """根据 skill_type 返回目标文件名。"""
    normalized = normalize_skill_type(skill_type)
    if normalized not in SKILL_TYPE_FILE_NAMES:
        raise ValueError(f"未知 skill_type：{skill_type}")
    return SKILL_TYPE_FILE_NAMES[normalized]


def load_analysis_state(source_analysis_task_id: str) -> Dict[str, Any]:
    """从本地 node_outputs 读取分析任务最终 state。"""
    snapshot_path = NODE_OUTPUT_DIR / source_analysis_task_id / "state.json"
    if not snapshot_path.exists():
        raise FileNotFoundError(f"未找到分析任务 state.json：{snapshot_path}")

    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    state = payload.get("state") if isinstance(payload, dict) else None
    if not isinstance(state, dict):
        raise ValueError(f"state.json 格式不正确：{snapshot_path}")
    return state


def filter_round_fields(rounds: Iterable[Any], skill_type: str) -> list[Dict[str, Any]]:
    """按 skill_type 裁剪 analysis_rounds。"""
    normalized = normalize_skill_type(skill_type)
    fields = ROUND_FIELDS_BY_SKILL_TYPE.get(normalized)
    if not fields:
        raise ValueError(f"未知 skill_type：{skill_type}")

    filtered: list[Dict[str, Any]] = []
    for item in rounds or []:
        if not isinstance(item, dict):
            continue
        filtered.append({field: item.get(field) for field in fields if field in item})
    return filtered


def build_artifact_context(analysis_state: Dict[str, Any], skill_type: str) -> Dict[str, Any]:
    """为单个 Skill 文件构造上下文。"""
    return {
        "question": analysis_state.get("question", ""),
        "analysis_rounds": filter_round_fields(analysis_state.get("analysis_rounds", []), skill_type),
    }


def build_artifact_spec(skill_type: str) -> Dict[str, Any]:
    """返回每类 Skill 文件的写作目标与检查重点。"""
    normalized = normalize_skill_type(skill_type)
    specs = {
        "SKILL": {
            "goal": "沉淀场景总说明，说明适用范围、核心问题类型、默认分析框架和必须避免的误判。",
            "must_include": ["场景适用范围", "这个场景要回答什么", "默认分析框架", "继续追证条件", "必须避免的行为"],
            "must_avoid": ["本次具体结论", "具体任务 ID", "具体文件路径", "只适用于单个数据表的规则"],
            "hard_constraints": [
                "文件必须以 YAML frontmatter 开头，且至少包含 name 和 description 两个字段，格式为：---\\nname: 场景名称\\ndescription: 场景适用说明\\n---。",
                "name 应是适合展示给用户看的中文场景名，description 应说明适用场景和边界。",
            ],
        },
        "metrics": {
            "goal": "沉淀该场景下可复用的指标/证据选择规则。",
            "must_include": ["核心指标或证据", "条件指标或证据", "适用条件", "辅助证据", "缺字段降级策略"],
            "must_avoid": ["把本次字段名写成唯一字段", "只列指标不说明用途", "缺少样本量和分母意识"],
            "hard_constraints": ["分析内容必须贴紧最开始定下的分析方向"],
        },
        "calculations": {
            "goal": "沉淀指标或证据的计算口径、字段需求、降级策略和计算限制。",
            "must_include": ["统一计算口径", "核心指标计算方式", "分母为 0 或字段缺失时的处理", "数据粒度要求", "估算口径说明"],
            "must_avoid": ["直接写 SQL", "臆造字段", "忽略口径一致性", "把一次查询结果当成固定计算规则"],
            "hard_constraints": ["分析内容必须贴紧最开始定下的分析方向"],
        },
        "analysis": {
            "goal": "沉淀该场景下的数据解释规则、证据强度、质量检查和因果表达边界。",
            "must_include": ["数据质量检查", "默认解释顺序", "样本量不足降级", "结论强度", "因果表达限制"],
            "must_avoid": ["把相关写成因果", "忽略数据质量问题", "复制本次分析结论"],
            "hard_constraints": ["分析内容必须贴紧最开始定下的分析方向"],
        },
        "report_template": {
            "goal": "沉淀该场景适用的报告结构和表达要求。",
            "must_include": ["推荐报告结构", "核心结论表达方式", "数据限制说明位置", "图表或表格引用原则"],
            "must_avoid": ["固定写死本次标题", "要求报告复述所有过程", "编造图表或数据"],
            "hard_constraints": ["分析内容必须贴紧最开始定下的分析方向"],
        },
    }
    if normalized not in specs:
        raise ValueError(f"未知 skill_type：{skill_type}")
    return specs[normalized]


def load_reference_skill_content(skill_type: str, reference_skill_name: str = "product_sales") -> str:
    """读取现有同类型 Skill 文件作为参考。"""
    file_name = skill_file_name(skill_type)
    skill_dir = SKILLS_ROOT / reference_skill_name
    candidates = [skill_dir / file_name]
    if file_name == "SKILL.md":
        candidates.append(skill_dir / "skill.md")

    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    return ""


def build_initial_state_from_analysis_task(
    source_analysis_task_id: str,
    skill_type: str,
    *,
    distillation_task_id: str | None = None,
    max_rounds: int = 3,
    reference_skill_name: str = "product_sales",
    scene_direction: str = "",
) -> Dict[str, Any]:
    """从本地分析任务 state 构造单文件沉淀初始 state。"""
    normalized = normalize_skill_type(skill_type)
    # 从本地分析任务的state里获取分析的内容
    analysis_state = load_analysis_state(source_analysis_task_id)
    resolved_task_id = distillation_task_id or uuid4().hex
    return {
        "task_id": resolved_task_id,
        "distillation_task_id": resolved_task_id,
        "source_analysis_task_id": source_analysis_task_id,
        "skill_type": normalized,
        "file_name": skill_file_name(normalized),
        "artifact_spec": build_artifact_spec(normalized),
        "context": build_artifact_context(analysis_state, normalized),
        "reference_skill_content": load_reference_skill_content(normalized, reference_skill_name),
        "scene_direction": scene_direction,
        "round_index": 1,
        "max_rounds": max_rounds,
        "revision_history": [],
        "status": "running",
    }
