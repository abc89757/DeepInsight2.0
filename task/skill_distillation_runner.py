"""Skill 沉淀任务后台执行器。"""

from __future__ import annotations

import json
import re
import shutil
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from graph.skill_distillation.context import (
    SKILL_TYPE_FILE_NAMES,
    build_initial_state_from_analysis_task,
)
from graph.skill_distillation.scene_direction.context import build_scene_direction_initial_state
from graph.skill_distillation.scene_direction.workflow import run_scene_direction_debate
from graph.skill_distillation.workflow import run_skill_artifact_distillation
from services.node_output_store import NODE_OUTPUT_DIR
from services.skill_scene_direction_persistence import (
    sync_skill_scene_direction_state_to_db,
    update_skill_scene_direction_task_stage,
)
from services.skill_scene_direction_task_service import create_skill_scene_direction_task
from services.skill_distillation_persistence import (
    sync_skill_artifact_state_to_db,
    sync_skill_distillation_task_state_to_db,
    update_skill_distillation_task_stage,
)
from services.skill_distillation_task_service import default_target_skill_name
from services.task_cancellation import TaskCancelled, cleanup_task_cancel, register_task
from services.task_events import close_task_events, publish_task_event


STATE_SNAPSHOT_FILENAME = "state.json"
SKILL_CANDIDATE_ROOT = Path("skill_candidates")
SKILLS_ROOT = Path("skills")
SENSITIVE_KEYS = {"password", "password_encrypted", "api_key", "token", "secret"}
INVALID_DIR_NAME_CHARS = r'<>:"/\|?*'


def _to_jsonable(value: Any) -> Any:
    """把沉淀任务 state 转成可写 JSON 的对象。"""
    if hasattr(value, "model_dump"):
        return _to_jsonable(value.model_dump())
    if hasattr(value, "dict"):
        return _to_jsonable(value.dict())
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text.lower() in SENSITIVE_KEYS:
                result[key_text] = "******" if item else ""
            else:
                result[key_text] = _to_jsonable(item)
        return result
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def save_state_snapshot(
    task_id: str,
    state: Dict[str, Any],
    stage: str,
    status: str = "running",
    error: str | None = None,
) -> str:
    """保存沉淀任务最新 state 到 node_outputs/{task_id}/state.json。"""
    task_output_dir = NODE_OUTPUT_DIR / task_id
    task_output_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = task_output_dir / STATE_SNAPSHOT_FILENAME
    temp_path = snapshot_path.with_suffix(".json.tmp")
    payload = {
        "_snapshot": {
            "task_id": task_id,
            "stage": stage,
            "status": status,
            "error": error,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
        "state": _to_jsonable(state),
    }
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(snapshot_path)
    return str(snapshot_path)


def update_task(task_store: Dict[str, Dict[str, Any]], task_id: str, **kwargs: Any) -> None:
    """更新内存中的沉淀任务状态。"""
    task = task_store.get(task_id)
    if not task:
        return
    task.update(kwargs)
    task["updated_at"] = datetime.now().isoformat(timespec="seconds")


def write_text_atomic(path: Path, content: str) -> str:
    """原子写入文本文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(content or "", encoding="utf-8")
    temp_path.replace(path)
    return str(path)


def write_candidate_file(candidate_dir: Path, file_name: str, content: str) -> str:
    """把单个 Skill 文件写入候选目录。"""
    return write_text_atomic(candidate_dir / file_name, content)


def extract_skill_name_from_markdown(content: str) -> str:
    """从 SKILL.md frontmatter 中提取 name。"""
    match = re.match(r"\s*---\s*\n(.*?)\n---", content or "", flags=re.DOTALL)
    if not match:
        return ""

    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        if key.strip() != "name":
            continue
        return value.strip().strip("\"'")
    return ""


def sanitize_skill_dir_name(name: str) -> str:
    """保留中文名作为目录名，只移除文件系统不允许的字符。"""
    cleaned = "".join("_" if char in INVALID_DIR_NAME_CHARS else char for char in (name or "").strip())
    return cleaned.strip().strip(".")


def resolve_final_skill_name(candidate_files: Dict[str, str], fallback: str) -> str:
    """从候选 SKILL.md 的 name 字段确定正式 Skill 目录名。"""
    skill_path = candidate_files.get("SKILL")
    if not skill_path:
        return fallback

    name = extract_skill_name_from_markdown(Path(skill_path).read_text(encoding="utf-8"))
    return sanitize_skill_dir_name(name) or fallback


def promote_candidate_files(
    candidate_files: Dict[str, str],
    target_skill_name: str,
    *,
    overwrite_existing: bool = False,
) -> Dict[str, str]:
    """把候选文件统一复制到正式 skills/{target_skill_name} 目录。"""
    final_dir = SKILLS_ROOT / target_skill_name
    if final_dir.exists() and not overwrite_existing:
        conflicts = [
            final_dir / Path(path).name
            for path in candidate_files.values()
            if (final_dir / Path(path).name).exists()
        ]
        if conflicts:
            names = ", ".join(path.name for path in conflicts)
            raise FileExistsError(f"目标 Skill 目录已存在同名文件，拒绝覆盖：{names}")

    final_dir.mkdir(parents=True, exist_ok=True)
    final_files: Dict[str, str] = {}
    for skill_type, source_path in candidate_files.items():
        source = Path(source_path)
        target = final_dir / source.name
        if overwrite_existing:
            shutil.copyfile(source, target)
        else:
            target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        final_files[skill_type] = str(target)
    return final_files


def run_skill_distillation_task(
    task_id: str,
    # 来源分析任务 ID
    source_analysis_task_id: str,
    task_store: Dict[str, Dict[str, Any]],
    *,
    # 最终要写入的 skill 文件夹名
    target_skill_name: Optional[str] = None,
    max_rounds: int = 3,
    max_debate_rounds: int = 3,
    reference_skill_name: str = "product_sales",
    promote_to_skills: bool = True,
    overwrite_existing: bool = False,
) -> None:
    """运行一次完整 Skill 沉淀任务。

    流程:
        1. 读取来源分析任务本地 state。
        2. 先运行场景定性辩论 graph，得到统一 scene_direction。
        3. 按五个 skill_type 构造单文件上下文。
        4. 依次调用单文件 Skill 沉淀 graph。
        5. 保存候选 md 文件。
        6. 全部成功后读取 SKILL.md 的 name，并统一写入 skills/{name}。
    """
    # 确定最终skill的名称，并创建候选目录
    resolved_skill_name = (target_skill_name or "").strip() or default_target_skill_name(source_analysis_task_id)
    resolved_max_debate_rounds = max(1, min(int(max_debate_rounds or 3), 10))
    candidate_dir = SKILL_CANDIDATE_ROOT / task_id
    candidate_dir.mkdir(parents=True, exist_ok=True)
    # 整次沉淀任务的总状态，不是单个文件 graph 的 state
    final_state: Dict[str, Any] = {
        "task_id": task_id,
        "task_type": "skill_distillation",
        "source_analysis_task_id": source_analysis_task_id,
        "target_skill_name": resolved_skill_name,
        "candidate_dir": str(candidate_dir),
        "status": "running",
        "stage": "start",
        "message": "Skill 沉淀任务已启动。",
        "skill_results": {},
    }
    # 存每个文件的候选路径
    candidate_files: Dict[str, str] = {}
    # 存每个 skill_type 跑完 graph 后的完整 state
    skill_states: Dict[str, Dict[str, Any]] = {}
    scene_direction_task_id: Optional[str] = None
    scene_direction_state: Dict[str, Any] = {}
    # 把任务注册到取消机制里
    register_task(task_id)

    try:
        # 更新内存TASK_STORE
        update_task(
            task_store,
            task_id,
            status="running",
            stage="start",
            message="Skill 沉淀任务已启动。",
            error=None,
        )
        # 更新数据库的任务状态
        update_skill_distillation_task_stage(
            task_id,
            stage="start",
            message="Skill 沉淀任务已启动。",
            status="running",
        )
        # 发布任务开始事件，预留的推送到前端用的
        publish_task_event(
            task_id,
            "task_started",
            {
                "stage": "start",
                "message": "Skill 沉淀任务已启动。",
            },
        )
        # 保存本地快照
        save_state_snapshot(task_id, final_state, stage="start")

        scene_message = "正在通过辩论确定本次 Skill 沉淀的统一场景方向。"
        final_state.update({"stage": "scene_direction", "message": scene_message, "status": "running"})
        update_task(task_store, task_id, status="running", stage="scene_direction", message=scene_message)
        update_skill_distillation_task_stage(
            task_id,
            stage="scene_direction",
            message=scene_message,
            status="running",
        )
        publish_task_event(
            task_id,
            "task_progress",
            {
                "stage": "scene_direction",
                "message": scene_message,
            },
        )

        scene_task = create_skill_scene_direction_task(
            distillation_task_id=task_id,
            source_analysis_task_id=source_analysis_task_id,
            max_debate_rounds=resolved_max_debate_rounds,
        )
        scene_direction_task_id = scene_task["task_id"]
        task_store[scene_direction_task_id] = scene_task
        register_task(scene_direction_task_id)
        update_skill_scene_direction_task_stage(
            scene_direction_task_id,
            stage="scene_direction",
            message=scene_message,
            status="running",
        )
        final_state["scene_direction_task_id"] = scene_direction_task_id
        save_state_snapshot(task_id, final_state, stage="scene_direction")

        scene_initial_state = build_scene_direction_initial_state(
            source_analysis_task_id=source_analysis_task_id,
            distillation_task_id=task_id,
            scene_direction_task_id=scene_direction_task_id,
            max_debate_rounds=resolved_max_debate_rounds,
            reference_skill_name=reference_skill_name,
        )
        save_state_snapshot(scene_direction_task_id, scene_initial_state, stage="scene_direction")
        scene_direction_state = run_scene_direction_debate(scene_initial_state)
        scene_direction = (scene_direction_state.get("scene_direction") or "").strip()
        if not scene_direction:
            raise ValueError("场景定性 graph 没有生成有效 scene_direction。")
        scene_direction_state.update(
            {
                "stage": "finished",
                "message": "Skill 场景定性任务执行完成。",
                "status": "succeeded",
            }
        )
        sync_skill_scene_direction_state_to_db(scene_direction_task_id, scene_direction_state)
        save_state_snapshot(
            scene_direction_task_id,
            scene_direction_state,
            stage="finished",
            status="succeeded",
        )
        update_task(
            task_store,
            scene_direction_task_id,
            status="succeeded",
            stage="finished",
            message="Skill 场景定性任务执行完成。",
            scene_direction=scene_direction,
        )
        final_state["scene_direction"] = scene_direction
        save_state_snapshot(task_id, final_state, stage="scene_direction")

        # 待沉淀的五类文件：SKILL/metrics/calculations/analysis/report_template
        for skill_type, file_name in SKILL_TYPE_FILE_NAMES.items():
            stage = f"distill_{skill_type}"
            message = f"正在沉淀 {file_name}。"
            print('==='*20)
            print(message)
            final_state.update({"stage": stage, "message": message, "status": "running"})
            update_task(task_store, task_id, status="running", stage=stage, message=message)
            update_skill_distillation_task_stage(task_id, stage=stage, message=message, status="running")

            # 构造单次任务的初始state
            initial_state = build_initial_state_from_analysis_task(
                source_analysis_task_id,
                skill_type,
                distillation_task_id=task_id,
                max_rounds=max_rounds,
                reference_skill_name=reference_skill_name,
                scene_direction=final_state.get("scene_direction", ""),
            )
            initial_state.update(
                {
                    "target_skill_name": resolved_skill_name,
                    "candidate_dir": str(candidate_dir),
                    "stage": stage,
                    "message": message,
                }
            )
            artifact_state = run_skill_artifact_distillation(initial_state)
            markdown_content = (artifact_state.get("markdown_content") or "").strip()
            if not markdown_content:
                raise ValueError(f"{skill_type} 没有生成有效 Markdown 内容。")

            candidate_file_path = write_candidate_file(candidate_dir, file_name, markdown_content)
            artifact_state.update(
                {
                    "candidate_file_path": candidate_file_path,
                    "stage": stage,
                    "message": f"{file_name} 候选文件已生成。",
                    "status": "succeeded",
                }
            )
            sync_skill_artifact_state_to_db(task_id, artifact_state)

            candidate_files[skill_type] = candidate_file_path
            skill_states[skill_type] = artifact_state
            final_state["skill_results"][skill_type] = {
                "file_name": file_name,
                "candidate_file_path": candidate_file_path,
                "evaluator_decision": artifact_state.get("evaluator_decision"),
                "final_score": artifact_state.get("final_score"),
                "completed_rounds": len(artifact_state.get("revision_history") or []),
            }
            save_state_snapshot(task_id, final_state, stage=stage)

        resolved_skill_name = resolve_final_skill_name(candidate_files, resolved_skill_name)
        final_state["target_skill_name"] = resolved_skill_name

        final_files = promote_candidate_files(
            candidate_files,
            resolved_skill_name,
            overwrite_existing=overwrite_existing,
        )
        for skill_type, final_file_path in final_files.items():
            skill_state = skill_states[skill_type]
            skill_state["final_file_path"] = final_file_path
            skill_state["target_skill_name"] = resolved_skill_name
            sync_skill_artifact_state_to_db(task_id, skill_state)
            final_state["skill_results"][skill_type]["final_file_path"] = final_file_path

        final_state.update(
            {
                "status": "finished",
                "stage": "finished",
                "message": "Skill 沉淀任务执行完成。",
                "final_skill_dir": str(SKILLS_ROOT / resolved_skill_name),
            }
        )
        snapshot_path = save_state_snapshot(task_id, final_state, stage="finished", status="finished")
        update_task(
            task_store,
            task_id,
            status="finished",
            stage="finished",
            message="Skill 沉淀任务执行完成。",
            state_snapshot_path=snapshot_path,
            error=None,
            skill_results=final_state.get("skill_results", {}),
        )
        sync_skill_distillation_task_state_to_db(task_id, final_state)
        publish_task_event(
            task_id,
            "task_finished",
            {
                "stage": "finished",
                "message": "Skill 沉淀任务执行完成。",
            },
        )

    except TaskCancelled as exc:
        print(f"[skill distillation {task_id}] cancelled: {exc}")
        final_state.update(
            {
                "status": "cancelled",
                "stage": "cancelled",
                "message": "Skill 沉淀任务已取消。",
                "error": None,
            }
        )
        save_state_snapshot(task_id, final_state, stage="cancelled", status="cancelled")
        update_task(task_store, task_id, status="cancelled", stage="cancelled", message="Skill 沉淀任务已取消。")
        sync_skill_distillation_task_state_to_db(task_id, final_state)
        if scene_direction_task_id and scene_direction_state.get("status") != "succeeded":
            scene_direction_state.update(
                {
                    "status": "cancelled",
                    "stage": "cancelled",
                    "message": "Skill 场景定性任务已取消。",
                }
            )
            sync_skill_scene_direction_state_to_db(scene_direction_task_id, scene_direction_state)
            save_state_snapshot(
                scene_direction_task_id,
                scene_direction_state,
                stage="cancelled",
                status="cancelled",
            )
        publish_task_event(task_id, "task_cancelled", {"stage": "cancelled", "message": "Skill 沉淀任务已取消。"})

    except Exception as exc:
        traceback.print_exc()
        final_state.update(
            {
                "status": "failed",
                "stage": "failed",
                "message": "Skill 沉淀任务执行失败。",
                "error": str(exc),
            }
        )
        save_state_snapshot(task_id, final_state, stage="failed", status="failed", error=str(exc))
        update_task(
            task_store,
            task_id,
            status="failed",
            stage="failed",
            message="Skill 沉淀任务执行失败。",
            error=str(exc),
        )
        sync_skill_distillation_task_state_to_db(task_id, final_state)
        if scene_direction_task_id and scene_direction_state.get("status") != "succeeded":
            scene_direction_state.update(
                {
                    "status": "failed",
                    "stage": scene_direction_state.get("stage") or "failed",
                    "message": "Skill 场景定性任务执行失败。",
                    "error": str(exc),
                }
            )
            sync_skill_scene_direction_state_to_db(scene_direction_task_id, scene_direction_state)
            save_state_snapshot(
                scene_direction_task_id,
                scene_direction_state,
                stage=scene_direction_state.get("stage") or "failed",
                status="failed",
                error=str(exc),
            )
        publish_task_event(
            task_id,
            "task_failed",
            {
                "stage": "failed",
                "message": "Skill 沉淀任务执行失败。",
                "error": str(exc),
            },
        )
    finally:
        cleanup_task_cancel(task_id)
        if scene_direction_task_id:
            cleanup_task_cancel(scene_direction_task_id)
            close_task_events(scene_direction_task_id)
        close_task_events(task_id)
