"""turn_stitcher web/document 内联材料。"""
from __future__ import annotations

from tasks.orchestration.turn_stitcher import TaskStitchSlot, stitch_slot_to_inline_material


def test_stitch_slot_to_inline_material_web() -> None:
    slot = TaskStitchSlot(
        task_id="task_web_1",
        summary_text="雅虎财经：Save Lily 事件要点摘要。",
        lane="web",
        attached_at="2026-06-03T12:00:00",
    )
    text = stitch_slot_to_inline_material(slot)
    assert "web" in text
    assert "Save Lily" in text
    assert text.startswith("【以下为已完成的后台任务摘要")
