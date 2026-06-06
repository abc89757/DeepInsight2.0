"""手动测试 Skill 自沉淀流程。

直接修改下面的常量后运行：
    python test_skill_distillation.py
"""

from __future__ import annotations

from pathlib import Path

from services.skill_distillation_execution import create_and_run_skill_distillation_task


SOURCE_ANALYSIS_TASK_ID = "99a6fc3ffaf94d95b4e76394e9cdaa6a"
TARGET_SKILL_NAME = None
TARGET_SKILL_DISPLAY_NAME = None
MAX_ROUNDS = 3
MAX_DEBATE_ROUNDS = 3
REFERENCE_SKILL_NAME = "product_sales"

# 默认只生成候选文件到 skill_candidates/{distillation_task_id}。
# 改成 True 后，会复制到正式 skills/{TARGET_SKILL_NAME}。
PROMOTE_TO_SKILLS = False
OVERWRITE_EXISTING = False


def main() -> None:
    """创建并运行一次 Skill 沉淀任务。"""
    source_task_id = SOURCE_ANALYSIS_TASK_ID.strip()
    if not source_task_id or source_task_id == "在这里填分析任务ID":
        raise ValueError("请先在 test_skill_distillation.py 里填写 SOURCE_ANALYSIS_TASK_ID。")

    source_state_path = Path("node_outputs") / source_task_id / "state.json"
    if not source_state_path.exists():
        raise FileNotFoundError(f"未找到来源分析任务 state.json：{source_state_path}")

    print("开始创建任务id")
    task_id = create_and_run_skill_distillation_task(
        source_analysis_task_id=source_task_id,
        target_skill_name=TARGET_SKILL_NAME,
        target_skill_display_name=TARGET_SKILL_DISPLAY_NAME,
        max_rounds=MAX_ROUNDS,
        max_debate_rounds=MAX_DEBATE_ROUNDS,
        reference_skill_name=REFERENCE_SKILL_NAME,
        promote_to_skills=PROMOTE_TO_SKILLS,
        overwrite_existing=OVERWRITE_EXISTING,
    )

    print(f"沉淀任务 ID：{task_id}")
    print(f"候选目录：skill_candidates/{task_id}")
    if PROMOTE_TO_SKILLS:
        target_name = TARGET_SKILL_NAME or f"skill_{source_task_id[:8]}"
        print(f"正式目录：skills/{target_name}")


if __name__ == "__main__":
    main()
