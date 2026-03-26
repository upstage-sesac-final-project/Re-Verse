"""Planner 노드 테스트.

[ 테스트 구조 ]
  - 입력(state) : 하드코딩된 mock 데이터 (Definition이 넘겨줄 값을 직접 작성)
  - LLM 호출   : 실제 API 호출 → .env의 LLM_API_KEY 필요
  - 검증        : execution_plan의 구조 및 내용 확인

[ 실행 방법 ]
  # 결과 출력 없이 검증만
  uv run pytest agent/tests/test_planner.py -v

  # LLM이 실제로 만든 execution_plan 내용까지 출력
  uv run pytest agent/tests/test_planner.py -v -s

  # 특정 테스트 함수 실행
  uv run pytest agent/tests/test_planner.py::test_planner_add_skill_to_actor -v -s

주의:
    실제 LLM API를 호출하므로 루트 .env에 LLM_API_KEY가 설정되어 있어야 합니다.
"""

import json
from typing import Any, cast

import pytest

from agent.graph.nodes.planner import planner
from agent.graph.state import AgentState

# ──────────────────────────────────────────────────────────────
# 공통 헬퍼
# ──────────────────────────────────────────────────────────────

VALID_ACTION_TYPES = {"query", "create", "update", "delete"}


def build_state(
    user_input: str,
    intent: str,
    modifications: list[dict],
    extracted_ids: dict,
    target_files: list[str],
) -> AgentState:
    """테스트용 AgentState를 생성한다.

    다른 노드와 통합 테스트 시 이 함수로 초기 state를 구성해 재사용할 수 있다.
    """
    return AgentState(
        user_input=user_input,
        intent=cast(Any, intent),
        modifications=modifications,
        extracted_ids=extracted_ids,
        target_files=target_files,
    )


def print_execution_plan(test_name: str, result: dict) -> None:
    """LLM이 생성한 execution_plan을 읽기 좋게 출력한다.

    pytest -s 옵션으로 실행할 때 실제 LLM 응답 내용을 확인할 수 있다.
    """
    plan = result.get("execution_plan", [])
    print(f"\n{'=' * 60}")
    print(f"[{test_name}] execution_plan ({len(plan)} steps)")
    print("=" * 60)
    for step in plan:
        print(f"\n  step {step['step_id']} [{step['action_type'].upper()}] {step['target_file']}")
        print(f"  설명     : {step['description']}")
        print(f"  target_info: {json.dumps(step['target_info'], ensure_ascii=False)}")
        print(f"  depends_on : {step['depends_on']}")
        if step["condition"]:
            print(f"  조건     : {step['condition']}")
    print("=" * 60)


def assert_execution_plan(result: dict, min_steps: int = 1) -> list[dict]:
    """execution_plan 기본 구조를 검증하고 plan 리스트를 반환한다."""
    assert "execution_plan" in result, "execution_plan 키가 없습니다"

    plan = result["execution_plan"]
    assert isinstance(plan, list), "execution_plan이 리스트가 아닙니다"
    assert len(plan) >= min_steps, f"step이 {min_steps}개 이상이어야 합니다 (실제: {len(plan)})"

    step_ids = []
    for step in plan:
        # 필수 필드 존재 여부
        for field in (
            "step_id",
            "description",
            "action_type",
            "target_file",
            "target_info",
            "depends_on",
            "condition",
        ):
            assert field in step, f"step에 '{field}' 필드가 없습니다: {step}"

        # 타입 검증
        assert isinstance(step["step_id"], int), "step_id가 int가 아닙니다"
        assert isinstance(step["description"], str) and step["description"], (
            "description이 비어 있습니다"
        )
        assert step["action_type"] in VALID_ACTION_TYPES, (
            f"action_type이 유효하지 않습니다: {step['action_type']}"
        )
        assert isinstance(step["target_file"], str) and step["target_file"], (
            "target_file이 비어 있습니다"
        )
        assert isinstance(step["target_info"], dict), "target_info가 dict가 아닙니다"
        assert isinstance(step["depends_on"], list), "depends_on이 리스트가 아닙니다"
        assert isinstance(step["condition"], str), "condition이 str가 아닙니다"

        step_ids.append(step["step_id"])

    # depends_on이 앞서 등장한 step_id만 참조하는지 검증
    seen = set()
    for step in plan:
        for dep in step["depends_on"]:
            assert dep in seen, (
                f"step {step['step_id']}의 depends_on={dep}이 아직 등장하지 않은 step을 참조합니다"
            )
        seen.add(step["step_id"])

    return plan


# ──────────────────────────────────────────────────────────────
# 테스트 케이스
# ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_planner_add_skill_to_actor1():
    """액터에게 스킬 추가 — 가장 복잡한 관계 (Actors → Classes → Skills) 테스트."""
    state = build_state(
        user_input="쥔공에게 치즈 폭탄 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_skill", "target": "actor", "skill_name": "치즈 폭탄"}],
        extracted_ids={"actor_id": 1},
        target_files=["Actors.json", "Skills.json"],
    )

    result = await planner(state)
    print_execution_plan("스킬 추가", result)
    plan = assert_execution_plan(result, min_steps=2)

    # Skills.json을 다루는 step이 반드시 포함되어야 함
    target_files_in_plan = {step["target_file"] for step in plan}
    assert "Skills.json" in target_files_in_plan, "Skills.json을 다루는 step이 없습니다"

    # 스킬을 액터에 연결하는 update step이 있어야 함
    # RPG Maker MZ에서 스킬 연결 경로는 두 가지:
    #   1. Actors.json traits[] — 해당 액터 단독 부여
    #   2. Classes.json learnings[] — 직업 전체에 스킬 학습 부여
    skill_link_steps = [
        s
        for s in plan
        if s["target_file"] in ("Actors.json", "Classes.json") and s["action_type"] == "update"
    ]
    assert skill_link_steps, (
        "Actors.json 또는 Classes.json에 스킬을 연결하는 update step이 없습니다"
    )

    # Planner는 game_context를 채우지 않는다 (Executor 담당)
    assert "game_context" not in result, (
        "Planner는 game_context를 반환하지 않아야 합니다 (Executor 담당)"
    )


@pytest.mark.asyncio
async def test_planner_add_skill_to_actor2():
    """액터에게 스킬 추가 — 가장 복잡한 관계 (Actors → Classes → Skills) 테스트."""
    state = build_state(
        user_input="주인공에게 파이어볼 스킬을 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_skill", "target": "actor", "skill_name": "파이어볼"}],
        extracted_ids={"actor_id": 1},
        target_files=["Actors.json", "Skills.json"],
    )

    result = await planner(state)
    print_execution_plan("스킬 추가", result)
    plan = assert_execution_plan(result, min_steps=2)

    # Skills.json을 다루는 step이 반드시 포함되어야 함
    target_files_in_plan = {step["target_file"] for step in plan}
    assert "Skills.json" in target_files_in_plan, "Skills.json을 다루는 step이 없습니다"

    # 스킬을 액터에 연결하는 update step이 있어야 함
    # RPG Maker MZ에서 스킬 연결 경로는 두 가지:
    #   1. Actors.json traits[] — 해당 액터 단독 부여
    #   2. Classes.json learnings[] — 직업 전체에 스킬 학습 부여
    skill_link_steps = [
        s
        for s in plan
        if s["target_file"] in ("Actors.json", "Classes.json") and s["action_type"] == "update"
    ]
    assert skill_link_steps, (
        "Actors.json 또는 Classes.json에 스킬을 연결하는 update step이 없습니다"
    )


@pytest.mark.asyncio
async def test_planner_add_enemy():
    """적(Enemy) 추가 — Enemies.json 단독 수정 테스트."""
    state = build_state(
        user_input="드래곤이라는 적을 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_enemy", "target": "enemy", "enemy_name": "드래곤"}],
        extracted_ids={},
        target_files=["Enemies.json"],
    )

    result = await planner(state)
    print_execution_plan("적 추가", result)
    plan = assert_execution_plan(result, min_steps=1)

    # Enemies.json을 다루는 step이 반드시 포함되어야 함
    enemy_steps = [s for s in plan if s["target_file"] == "Enemies.json"]
    assert enemy_steps, "Enemies.json을 다루는 step이 없습니다"


@pytest.mark.asyncio
async def test_planner_add_npc_to_map():
    """맵에 NPC 추가 — Map*.json events 수정 테스트."""
    state = build_state(
        user_input="1번 맵에 마을 촌장 NPC를 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_npc", "target": "map", "map_id": 1, "npc_name": "마을 촌장"}],
        extracted_ids={"map_id": 1},
        target_files=["Map001.json"],
    )

    result = await planner(state)
    print_execution_plan("NPC 추가", result)
    plan = assert_execution_plan(result, min_steps=1)

    map_steps = [s for s in plan if "Map" in s["target_file"]]
    assert map_steps, "Map 파일을 다루는 step이 없습니다"


@pytest.mark.asyncio
async def test_planner_add_item():
    """아이템 추가 — Items.json 단독 수정 테스트."""
    state = build_state(
        user_input="불의 마법서라는 아이템을 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_item", "target": "item", "item_name": "불의 마법서"}],
        extracted_ids={},
        target_files=["Items.json"],
    )

    result = await planner(state)
    print_execution_plan("아이템 추가", result)
    plan = assert_execution_plan(result, min_steps=1)

    item_steps = [s for s in plan if s["target_file"] == "Items.json"]
    assert item_steps, "Items.json을 다루는 step이 없습니다"


@pytest.mark.asyncio
async def test_planner_modify_enemy_stat():
    """기존 적 스탯 수정 — 존재 여부 query 후 update 순서 테스트."""
    state = build_state(
        user_input="슬라임의 HP를 500으로 올려줘",
        intent="game_modify",
        modifications=[
            {
                "type": "update_stat",
                "target": "enemy",
                "enemy_name": "슬라임",
                "field": "hp",
                "value": 500,
            }
        ],
        extracted_ids={"enemy_name": "슬라임"},
        target_files=["Enemies.json"],
    )

    result = await planner(state)
    print_execution_plan("적 스탯 수정", result)
    plan = assert_execution_plan(result, min_steps=1)

    # query step이 update step보다 먼저 나와야 함
    action_types_in_order = [s["action_type"] for s in plan]
    if "query" in action_types_in_order and "update" in action_types_in_order:
        assert action_types_in_order.index("query") < action_types_in_order.index("update"), (
            "query step이 update step보다 먼저 나와야 합니다"
        )


@pytest.mark.asyncio
async def test_planner_returns_no_game_context():
    """Planner는 game_context를 채우지 않는다."""
    state = build_state(
        user_input="주인공에게 파이어볼 스킬을 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_skill", "target": "actor", "skill_name": "파이어볼"}],
        extracted_ids={"actor_id": 1},
        target_files=["Actors.json", "Skills.json"],
    )

    result = await planner(state)

    assert "game_context" not in result, (
        "Planner는 game_context를 반환하지 않아야 합니다 (Executor 담당)"
    )


@pytest.mark.asyncio
async def test_planner_step_dependency_order():
    """depends_on이 항상 선행 step만 참조하는지 검증."""
    state = build_state(
        user_input="주인공에게 아이스 볼트 스킬을 추가해줘",
        intent="game_modify",
        modifications=[{"type": "add_skill", "target": "actor", "skill_name": "아이스 볼트"}],
        extracted_ids={"actor_id": 1},
        target_files=["Actors.json", "Skills.json"],
    )

    result = await planner(state)
    print_execution_plan("의존성 순서 검증", result)
    # assert_execution_plan 내부에서 depends_on 순서 검증이 포함됨
    assert_execution_plan(result, min_steps=1)
