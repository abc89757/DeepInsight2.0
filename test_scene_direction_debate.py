"""手动测试 Skill 场景定性辩论流程。

直接修改下面的常量后运行：
    python test_scene_direction_debate.py
"""

from __future__ import annotations

from pathlib import Path

from graph.skill_distillation.scene_direction.context import build_scene_direction_initial_state
from graph.skill_distillation.scene_direction.workflow import run_scene_direction_debate
from services.skill_distillation_task_service import create_skill_distillation_task
from services.skill_scene_direction_persistence import (
    sync_skill_scene_direction_state_to_db,
    update_skill_scene_direction_task_stage,
)
from services.skill_scene_direction_task_service import create_skill_scene_direction_task
from services.task_cancellation import cleanup_task_cancel, register_task
from task.skill_distillation_runner import save_state_snapshot
from task_store import TASK_STORE


SOURCE_ANALYSIS_TASK_ID = "99a6fc3ffaf94d95b4e76394e9cdaa6a"
TARGET_SKILL_NAME = None
TARGET_SKILL_DISPLAY_NAME = None
MAX_DEBATE_ROUNDS = 3
REFERENCE_SKILL_NAME = "product_sales"


def main() -> None:
    """创建并运行一次场景定性辩论任务。"""
    source_task_id = SOURCE_ANALYSIS_TASK_ID.strip()
    if not source_task_id or source_task_id == "在这里填分析任务ID":
        raise ValueError("请先在 test_scene_direction_debate.py 里填写 SOURCE_ANALYSIS_TASK_ID。")

    source_state_path = Path("node_outputs") / source_task_id / "state.json"
    if not source_state_path.exists():
        raise FileNotFoundError(f"未找到来源分析任务 state.json：{source_state_path}")

    print("创建父级 Skill 沉淀任务记录")
    distillation_task = create_skill_distillation_task(
        source_analysis_task_id=source_task_id,
        target_skill_name=TARGET_SKILL_NAME,
        target_skill_display_name=TARGET_SKILL_DISPLAY_NAME,
        max_rounds=1,
    )
    distillation_task_id = distillation_task["task_id"]
    TASK_STORE[distillation_task_id] = distillation_task

    print("创建场景定性辩论任务记录")
    scene_task = create_skill_scene_direction_task(
        distillation_task_id=distillation_task_id,
        source_analysis_task_id=source_task_id,
        max_debate_rounds=MAX_DEBATE_ROUNDS,
    )
    scene_direction_task_id = scene_task["task_id"]
    TASK_STORE[scene_direction_task_id] = scene_task
    register_task(scene_direction_task_id)

    try:
        update_skill_scene_direction_task_stage(
            scene_direction_task_id,
            stage="scene_direction",
            message="正在通过辩论确定本次 Skill 沉淀的统一场景方向。",
            status="running",
        )
        initial_state = build_scene_direction_initial_state(
            source_analysis_task_id=source_task_id,
            distillation_task_id=distillation_task_id,
            scene_direction_task_id=scene_direction_task_id,
            max_debate_rounds=MAX_DEBATE_ROUNDS,
            reference_skill_name=REFERENCE_SKILL_NAME,
        )
        save_state_snapshot(scene_direction_task_id, initial_state, stage="scene_direction")

        final_state = run_scene_direction_debate(initial_state)
        final_state.update(
            {
                "stage": "finished",
                "message": "Skill 场景定性辩论测试完成。",
                "status": "succeeded",
            }
        )
        sync_skill_scene_direction_state_to_db(scene_direction_task_id, final_state)
        save_state_snapshot(scene_direction_task_id, final_state, stage="finished", status="succeeded")

        print(f"父级沉淀任务 ID：{distillation_task_id}")
        print(f"场景定性任务 ID：{scene_direction_task_id}")
        print(f"状态文件：node_outputs/{scene_direction_task_id}/state.json")
        print(f"辩论轮数：{final_state.get('debate_round')}")
        print(f"裁判判断：{final_state.get('judge_decision')}")
        print(f"最终选手：{final_state.get('selected_debater_id')}")
        print("\n最终场景方向：")
        print(final_state.get("scene_direction", ""))

    except Exception as exc:
        final_state = {
            "task_id": scene_direction_task_id,
            "scene_direction_task_id": scene_direction_task_id,
            "distillation_task_id": distillation_task_id,
            "source_analysis_task_id": source_task_id,
            "status": "failed",
            "stage": "failed",
            "message": "Skill 场景定性辩论测试失败。",
            "error": str(exc),
        }
        sync_skill_scene_direction_state_to_db(scene_direction_task_id, final_state)
        save_state_snapshot(scene_direction_task_id, final_state, stage="failed", status="failed", error=str(exc))
        raise
    finally:
        cleanup_task_cancel(scene_direction_task_id)


if __name__ == "__main__":
    main()

