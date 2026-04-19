"""executor_v2 의 Actor.classId 주입 — 이전 Classes.create 결과를 받아 덮기."""

from __future__ import annotations

from pathlib import Path

from agent.editor.nodes.executor_v2 import _inject_prev_results


def _prev_class_result(sid: int = 0, entity_id: int = 5) -> dict:
    return {
        "step_id": sid,
        "target_file": "Classes.json",
        "success": True,
        "entity_id": entity_id,
        "action": "create",
    }


class TestClassIdInjection:
    def test_inject_when_classid_none_and_prev_class_create_exists(self, tmp_path: Path):
        """Actor create 의 classId=None 일 때 이전 Classes.json create 의 id 로 채움."""
        target_info = {"name": "루나", "classId": None}
        step_results = {0: _prev_class_result(sid=0, entity_id=5)}
        out = _inject_prev_results(target_info, depends_on=[0], step_results=step_results, data_path=tmp_path)
        assert out["classId"] == 5

    def test_no_inject_when_classid_set(self, tmp_path: Path):
        """classId 가 이미 세팅돼 있으면 덮어쓰지 않음."""
        target_info = {"name": "루나", "classId": 3}
        step_results = {0: _prev_class_result(sid=0, entity_id=5)}
        out = _inject_prev_results(target_info, depends_on=[0], step_results=step_results, data_path=tmp_path)
        assert out["classId"] == 3

    def test_no_inject_when_no_prev_class(self, tmp_path: Path):
        """이전 Classes.json create 가 없으면 None 유지."""
        target_info = {"name": "루나", "classId": None}
        step_results = {0: {"step_id": 0, "target_file": "Weapons.json", "success": True, "entity_id": 9}}
        out = _inject_prev_results(target_info, depends_on=[0], step_results=step_results, data_path=tmp_path)
        assert out.get("classId") is None

    def test_inject_uses_step_results_even_without_depends_on(self, tmp_path: Path):
        """depends_on 이 비어도 step_results 에 있는 prev Classes 를 사용 (auto-prepend 경로)."""
        target_info = {"name": "루나", "classId": None}
        step_results = {0: _prev_class_result(sid=0, entity_id=7)}
        out = _inject_prev_results(target_info, depends_on=[], step_results=step_results, data_path=tmp_path)
        assert out["classId"] == 7

    def test_updates_path_still_works(self, tmp_path: Path):
        """기존 updates.classId=None 경로도 회귀 없는지."""
        target_info = {"id": 1, "updates": {"classId": None}}
        step_results = {0: _prev_class_result(sid=0, entity_id=5)}
        out = _inject_prev_results(target_info, depends_on=[0], step_results=step_results, data_path=tmp_path)
        assert out["updates"]["classId"] == 5
