"""Executor MVP 테스트

기본적인 동작 확인용 테스트들
"""

import asyncio
import importlib
import json
import logging
import uuid
from pathlib import Path

import pytest

from agent.graph.nodes.executor import executor
from agent.graph.state import AgentState
from app.backend.services.json_modify_tools.managers.actor_manager import ActorManager
from app.backend.services.json_modify_tools.managers.class_manager import ClassManager
from app.backend.services.json_modify_tools.managers.skill_manager import SkillManager
from app.backend.services.json_modify_tools.managers.system_manager import SystemManager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


_TEST_GAME_ID = f"game_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _ensure_test_game_data():
    """STORAGE_PATH/{_TEST_GAME_ID}/data/ 에 최소 JSON 생성."""
    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    if (data_path / "Actors.json").exists():
        return

    data_path.mkdir(parents=True, exist_ok=True)

    _base_system = {
        "gameTitle": "테스트 게임",
        "versionId": 1,
        "locale": "ko_KR",
        "startMapId": 1,
        "startX": 5,
        "startY": 5,
        "variables": [""] * 100,
        "switches": [""] * 100,
        "currencyUnit": "G",
        "windowTone": [0, 0, 0, 0],
        "battleBgm": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
        "battleback1Name": "",
        "battleback2Name": "",
        "partyMembers": [1],
        "testBattlers": [],
        "terms": {"basic": [], "commands": [], "params": [], "messages": {}},
    }
    _base_actors = [
        None,
        {
            "id": 1,
            "name": "용사",
            "nickname": "",
            "classId": 1,
            "initialLevel": 1,
            "maxLevel": 99,
            "characterName": "Actor1",
            "characterIndex": 0,
            "faceName": "Actor1",
            "faceIndex": 0,
            "battlerName": "Actor1_1",
            "equips": [0, 0, 0, 0, 0],
            "traits": [],
            "note": "",
            "profile": "",
        },
        {
            "id": 2,
            "name": "리드",
            "nickname": "",
            "classId": 1,
            "initialLevel": 1,
            "maxLevel": 99,
            "characterName": "Actor1",
            "characterIndex": 1,
            "faceName": "Actor1",
            "faceIndex": 1,
            "battlerName": "Actor1_2",
            "equips": [0, 0, 0, 0, 0],
            "traits": [],
            "note": "",
            "profile": "",
        },
    ]
    _base_classes = [
        None,
        {
            "id": 1,
            "name": "전사",
            "expParams": [30, 20, 30, 30],
            "params": [[0] * 99] * 8,
            "learnings": [],
            "traits": [],
            "note": "",
        },
    ]
    _base_skills = [
        None,
        {
            "id": 1,
            "name": "공격",
            "description": "",
            "iconIndex": 76,
            "mpCost": 0,
            "scope": 1,
            "occasion": 1,
            "damage": {"type": 1, "elementId": -1, "formula": "a.atk * 4 - b.def * 2"},
            "effects": [],
            "note": "",
        },
    ]
    _base_items = [None]

    for fname, data in [
        ("System.json", _base_system),
        ("Actors.json", _base_actors),
        ("Classes.json", _base_classes),
        ("Skills.json", _base_skills),
        ("Items.json", _base_items),
        ("Enemies.json", [None]),
    ]:
        (data_path / fname).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.mark.integration
async def test_executor_mvp():
    """MVP 기본 동작 테스트"""

    print("🧪 Executor MVP 테스트 시작")

    # ── 테스트 1: 기본 스킬 추가 ─────────────────────────────
    test_state = {
        "execution_plan": [
            {"task": "파이어볼 스킬 추가해줘", "description": "새로운 화염 공격 스킬"}
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    print("\n📝 테스트 1: 스킬 추가")
    print(f"입력: {test_state['execution_plan']}")

    try:
        result = await executor(test_state)

        print("✅ 실행 결과:")
        print(f"   - 성공 여부: {any(log.get('success') for log in result.get('changes_log', []))}")
        print(f"   - 변경 로그: {len(result.get('changes_log', []))}개")
        print(f"   - 백업 파일: {len(result.get('backup_paths', {}))}개")

        # 상세 로그 출력
        for i, log in enumerate(result.get("changes_log", [])):
            print(
                f"   - 로그 {i + 1}: {log.get('tool_name')} → {log.get('success')} ({log.get('stdout', log.get('error', 'N/A'))})"
            )

    except Exception as e:
        print(f"❌ 테스트 1 실패: {e}")

    # ── 테스트 2: 레벨 설정 ──────────────────────────────────
    test_state2 = {
        "execution_plan": [{"task": "주인공 레벨 50으로 설정해줘"}],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    print("\n📝 테스트 2: 레벨 설정")
    print(f"입력: {test_state2['execution_plan']}")

    try:
        result2 = await executor(test_state2)

        success_count = sum(1 for log in result2.get("changes_log", []) if log.get("success"))
        total_count = len(result2.get("changes_log", []))

        print(f"✅ 실행 결과: {success_count}/{total_count} 성공")

    except Exception as e:
        print(f"❌ 테스트 2 실패: {e}")

    # ── 테스트 3: 재시도 로직 ────────────────────────────────
    test_state3 = {
        "execution_plan": [{"task": "유효하지 않은 명령"}],
        "game_id": _TEST_GAME_ID,
        "retry_count": 3,  # 최대치 초과
    }

    print("\n📝 테스트 3: 재시도 한계 테스트")

    try:
        result3 = await executor(test_state3)

        if any("재시도" in log.get("error", "") for log in result3.get("changes_log", [])):
            print("✅ 재시도 한계 정상 동작")
        else:
            print("❌ 재시도 한계 로직 문제")

    except Exception as e:
        print(f"❌ 테스트 3 실패: {e}")

    print("\n🎉 MVP 테스트 완료")


async def test_structured_execution_plan_actors(monkeypatch):
    """3단계 구조화 execution_plan: Actors.json query → 조건부 create."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    unique_name = f"ZZZ_EXECUTOR_STRUCT_TEST_{uuid.uuid4().hex[:8]}"
    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": f"Actors.json에서 '{unique_name}' 존재 여부 조회",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_name": unique_name},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": f"{unique_name} 없으면 신규 생성",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": unique_name},
                "depends_on": [1],
                "condition": "step 1에서 캐릭터가 존재하지 않을 경우",
            },
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    logs = result.get("changes_log", [])
    assert len(logs) >= 2
    q = next(
        (x for x in logs if x.get("tool_name") in ("structured_actors_query", "get_actor")), None
    )
    c = next(
        (x for x in logs if x.get("tool_name") in ("structured_actors_create", "create_actor")),
        None,
    )
    assert q is not None and q.get("success") is True
    assert q.get("exists") is False
    assert c is not None and c.get("success") is True

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    mgr = ActorManager(data_path, "test_verify")
    verify = await mgr.execute("query", actor_name=unique_name)
    assert verify.get("exists") is True

    result2 = await executor(state)
    logs2 = result2.get("changes_log", [])
    skipped = [x for x in logs2 if x.get("skipped")]
    assert any("존재" in (x.get("skip_reason") or "") for x in skipped)


async def test_structured_execution_plan_full_update_flow(monkeypatch):
    """Classes/Actors/System 연계 query-create-update가 모두 동작하는지 검증."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    unique_suffix = uuid.uuid4().hex[:8]
    class_name = f"ZZZ_CLASS_{unique_suffix}"
    actor_name = f"ZZZ_ACTOR_{unique_suffix}"

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": f"Classes.json에서 '{class_name}' 클래스 존재 여부 조회",
                "action_type": "query",
                "target_file": "Classes.json",
                "target_info": {"class_name": class_name},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": f"{class_name} 클래스가 없으면 생성",
                "action_type": "create",
                "target_file": "Classes.json",
                "target_info": {"class_name": class_name},
                "depends_on": [1],
                "condition": "step 1에서 클래스가 존재하지 않을 경우",
            },
            {
                "step_id": 3,
                "description": f"Actors.json에서 '{actor_name}' 액터 존재 여부 조회",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_name": actor_name},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 4,
                "description": f"{actor_name} 액터가 없으면 생성",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": actor_name},
                "depends_on": [3],
                "condition": "step 3에서 액터가 존재하지 않을 경우",
            },
            {
                "step_id": 5,
                "description": "액터 classId를 클래스 인덱스로 업데이트",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"actor_name": actor_name, "class_name": class_name},
                "depends_on": [1, 2, 3, 4],
                "condition": "",
            },
            {
                "step_id": 6,
                "description": "System.partyMembers에 액터 추가",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"actor_name": actor_name},
                "depends_on": [5],
                "condition": "",
            },
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    logs = result.get("changes_log", [])
    assert any(x.get("tool_name") == "structured_classes_query" for x in logs)
    assert any(x.get("tool_name") == "structured_classes_create" for x in logs)
    assert any(x.get("tool_name") == "structured_actors_query" for x in logs)
    assert any(x.get("tool_name") == "structured_actors_create" for x in logs)
    assert any(
        x.get("tool_name") == "structured_actors_update" and x.get("success") is True for x in logs
    )
    assert any(
        x.get("tool_name") == "structured_system_update" and x.get("success") is True for x in logs
    )

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    class_mgr = ClassManager(data_path, "verify_class")
    actor_mgr = ActorManager(data_path, "verify_actor")
    system_mgr = SystemManager(data_path, "verify_system")

    class_q = await class_mgr.execute("query", class_name=class_name)
    actor_q = await actor_mgr.execute("query", actor_name=actor_name)
    assert class_q.get("exists") is True
    assert actor_q.get("exists") is True

    actor_update = await actor_mgr.execute(
        "update_class", target_info={"actor_name": actor_name, "class_name": class_name}
    )
    assert actor_update.get("success") is True

    system_update = await system_mgr.execute(
        "add_party_member", target_info={"actor_name": actor_name}
    )
    assert system_update.get("success") is True


async def test_skill_manager_directly():
    """SkillManager 직접 테스트"""

    print("\n🛠️ SkillManager 직접 테스트")

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"

    if not data_path.exists():
        print(f"❌ 데이터 경로 없음: {data_path}")
        return

    skill_manager = SkillManager(data_path, "direct_test")

    # 스킬 추가 테스트
    try:
        result = await skill_manager.execute(
            action="add", target_name="테스트볼", mpCost=30, description="테스트용 스킬"
        )

        print(
            f"스킬 추가 결과: {result.get('success')} - {result.get('message', result.get('error'))}"
        )

    except Exception as e:
        print(f"❌ SkillManager 테스트 실패: {e}")


def check_game_files():
    """게임 파일 존재 여부 체크"""

    print("\n📂 게임 파일 체크")

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    required_files = ["Skills.json", "Enemies.json", "Items.json"]

    for file_name in required_files:
        file_path = data_path / file_name
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"✅ {file_name}: {size} bytes")
        else:
            print(f"❌ {file_name}: 파일 없음")


@pytest.mark.asyncio
async def test_structured_mcp_alias_actor_update_routes_update_actor(monkeypatch):
    """4단계에서 Actors update + updates를 MCP update_actor로 정규화한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = arguments
        called["path_arg_name"] = path_arg_name
        return {"success": True, "data": {"ok": True}, "modified_files": ["Actors.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 기본 속성 업데이트",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {
                    "actor_id": 1,
                    "updates": {"nickname": "용사", "initialLevel": 5},
                },
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "update_actor"
    assert called["tool_name"] == "update_actor"
    assert called["arguments"] == {"actorId": 1, "updates": {"nickname": "용사", "initialLevel": 5}}


@pytest.mark.asyncio
async def test_structured_mcp_actor_update_merges_top_level_max_level(monkeypatch):
    """플래너가 maxLevel을 updates 밖에 두어도 update_actor 인자에 합쳐진다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = dict(arguments or {})
        return {"success": True, "data": {"ok": True}, "modified_files": ["Actors.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "maxLevel만 최상위로 준 업데이트",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"actor_id": 4, "maxLevel": 77},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "update_actor"
    assert called["arguments"] == {"actorId": 4, "updates": {"maxLevel": 77}}


@pytest.mark.asyncio
async def test_structured_mcp_actor_update_snake_case_maps_to_schema(monkeypatch):
    """snake_case 키는 Actor 스키마 camelCase로 매핑되어 updates에 들어간다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["arguments"] = dict(arguments or {})
        return {"success": True, "data": {"ok": True}, "modified_files": ["Actors.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "snake_case 필드",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"actor_id": 2, "initial_level": 10, "face_index": 5},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    await executor(state)
    assert called["arguments"] == {
        "actorId": 2,
        "updates": {"initialLevel": 10, "faceIndex": 5},
    }


@pytest.mark.asyncio
async def test_structured_mcp_alias_system_update_game_title(monkeypatch):
    """System update + game_title이 MCP update_game_title로 정규화되는지 검증."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = arguments
        return {"success": True, "data": {"ok": True}, "modified_files": ["System.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "게임 타이틀 수정",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"game_title": "MCP TEST TITLE"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "update_game_title"
    assert called["tool_name"] == "update_game_title"
    assert called["arguments"] == {"title": "MCP TEST TITLE"}


@pytest.mark.asyncio
async def test_structured_mcp_alias_system_update_starting_position(monkeypatch):
    """System update(map_id/x/y)가 MCP update_starting_position으로 정규화되는지 검증."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = arguments
        return {"success": True, "data": {"ok": True}, "modified_files": ["System.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "시작 위치 수정",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"map_id": "2", "x": "10", "y": 11},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "update_starting_position"
    assert called["tool_name"] == "update_starting_position"
    assert called["arguments"] == {"mapId": 2, "x": 10, "y": 11}


@pytest.mark.asyncio
async def test_actors_query_by_id_legacy_when_mcp_off(monkeypatch):
    """MCP 비활성 시 Actors query+actor_id(query_by_id)가 ActorManager 레거시로 동작해야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 ID 조회 (레거시)",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_id": 1},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "structured_actors_query_by_id"
    assert log["success"] is True
    assert log.get("exists") is True


@pytest.mark.asyncio
async def test_actors_list_search_legacy_when_mcp_off(monkeypatch):
    """MCP 비활성 시 Actors list/search가 ActorManager 레거시로 동작해야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    state_list: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 목록",
                "action_type": "list",
                "target_file": "Actors.json",
                "target_info": {},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }
    result_list = await executor(state_list)
    log1 = result_list["changes_log"][0]
    assert log1["tool_name"] == "structured_actors_list"
    assert log1["success"] is True
    assert "id=1:" in (log1.get("stdout") or "")

    state_search: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "이름 검색",
                "action_type": "search",
                "target_file": "Actors.json",
                "target_info": {"searchTerm": "리드"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }
    result_search = await executor(state_search)
    log2 = result_search["changes_log"][0]
    assert log2["tool_name"] == "structured_actors_search"
    assert log2["success"] is True
    assert log2.get("exists") is True


@pytest.mark.asyncio
async def test_actors_update_class_inherits_actor_id_from_create(monkeypatch):
    """생성 step 직후 update에 actor_id가 없어도 depends_on으로 classId 변경이 되어야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    unique_name = f"ZZZ_UPD_CLS_{uuid.uuid4().hex[:8]}"
    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 생성",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": unique_name},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": "classId만 변경 (actor_id 생략)",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"class_id": 2},
                "depends_on": [1],
                "condition": "",
            },
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }
    result = await executor(state)
    logs = result.get("changes_log", [])
    assert len(logs) == 2
    assert logs[0].get("tool_name") == "structured_actors_create"
    assert logs[0].get("success") is True
    assert logs[1].get("tool_name") == "structured_actors_update"
    assert logs[1].get("success") is True

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    mgr = ActorManager(data_path, "verify_upd_cls")
    verify = await mgr.execute("query", actor_name=unique_name)
    assert verify.get("exists") is True
    data = mgr.load_json_data()
    idx = verify.get("actor_id")
    assert idx is not None and isinstance(data[idx], dict)
    assert int(data[idx].get("classId") or 0) == 2


@pytest.mark.asyncio
async def test_actors_update_rename_by_new_name_after_create(monkeypatch):
    """actor_id + new_name만으로 update_actor(이름 변경)가 되어야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    old_name = f"ZZZ_REN_{uuid.uuid4().hex[:8]}"
    new_name = f"{old_name}_NEW"
    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 생성",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": old_name},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": "이름 변경",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"new_name": new_name},
                "depends_on": [1],
                "condition": "",
            },
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }
    result = await executor(state)
    logs = result.get("changes_log", [])
    assert logs[1].get("tool_name") == "structured_actors_update_general"
    assert logs[1].get("success") is True

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    mgr = ActorManager(data_path, "verify_ren")
    assert (await mgr.execute("query", actor_name=old_name)).get("exists") is False
    assert (await mgr.execute("query", actor_name=new_name)).get("exists") is True


@pytest.mark.asyncio
async def test_actors_rename_reconciles_wrong_planner_actor_id(monkeypatch):
    """actor_name이 있으면 플래너의 잘못된 actor_id를 무시하고 이름으로 행을 찾는다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: False)

    unique = f"ZZZ_RID_{uuid.uuid4().hex[:8]}"
    new_name = f"{unique}_REN"
    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 생성",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": unique},
                "depends_on": [],
                "condition": "",
            },
            {
                "step_id": 2,
                "description": "이름 변경(잘못된 actor_id 포함)",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {
                    "actor_name": unique,
                    "actor_id": 99999,
                    "new_name": new_name,
                },
                "depends_on": [1],
                "condition": "",
            },
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }
    result = await executor(state)
    logs = result.get("changes_log", [])
    assert logs[1].get("tool_name") == "structured_actors_update_general"
    assert logs[1].get("success") is True

    from app.backend.core.config import settings

    data_path = Path(settings.STORAGE_PATH) / _TEST_GAME_ID / "data"
    mgr = ActorManager(data_path, "verify_rid")
    assert (await mgr.execute("query", actor_name=unique)).get("exists") is False
    assert (await mgr.execute("query", actor_name=new_name)).get("exists") is True


@pytest.mark.asyncio
async def test_structured_mcp_alias_actor_query_by_id(monkeypatch):
    """Actors query + actor_id가 MCP get_actor(query_by_id)로 정규화되는지 검증."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = arguments
        return {"success": True, "data": {"id": 3, "name": "Harold"}, "modified_files": []}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 ID 조회",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_id": "3"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "get_actor"
    assert called["tool_name"] == "get_actor"
    assert called["arguments"] == {"actorId": 3}


@pytest.mark.asyncio
async def test_structured_mcp_alias_system_update_set_variable_name(monkeypatch):
    """System update(variable_id + name)가 MCP set_variable_name으로 정규화되는지 검증."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = arguments
        return {"success": True, "data": {"ok": True}, "modified_files": ["System.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "변수 이름 설정",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"variable_id": "7", "name": "quest_progress"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "set_variable_name"
    assert called["tool_name"] == "set_variable_name"
    assert called["arguments"] == {"variableId": 7, "name": "quest_progress"}


@pytest.mark.asyncio
async def test_structured_mcp_alias_system_update_set_switch_name(monkeypatch):
    """System update(switch_id + name)가 MCP set_switch_name으로 정규화되는지 검증."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    called: dict[str, object] = {}

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        called["tool_name"] = tool_name
        called["arguments"] = arguments
        return {"success": True, "data": {"ok": True}, "modified_files": ["System.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "스위치 이름 설정",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"switch_id": 9, "name": "door_opened"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "set_switch_name"
    assert called["tool_name"] == "set_switch_name"
    assert called["arguments"] == {"switchId": 9, "name": "door_opened"}


@pytest.mark.asyncio
async def test_mcp_failure_fallback_policy_actors_create(monkeypatch):
    """MCP 실패 시 레거시 분기가 있는 액션은 폴백되어 성공할 수 있어야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    unique_name = f"ZZZ_MCP_FALLBACK_{uuid.uuid4().hex[:8]}"

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        return {"success": False, "error": "simulated mcp failure"}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "액터 생성(MCP 실패 후 폴백)",
                "action_type": "create",
                "target_file": "Actors.json",
                "target_info": {"actor_name": unique_name},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "structured_actors_create"
    assert log["success"] is True


@pytest.mark.asyncio
async def test_mcp_failure_abort_policy_system_update_game_title(monkeypatch):
    """MCP 실패 시 레거시 분기가 있는 System update_game_title은 폴백 성공해야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        return {"success": False, "error": "simulated mcp failure"}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "게임 타이틀 변경(MCP 전용 경로)",
                "action_type": "update",
                "target_file": "System.json",
                "target_info": {"game_title": "ABORT_POLICY_TEST"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    assert log["tool_name"] == "structured_system_update_game_title"
    assert log["success"] is True


@pytest.mark.asyncio
async def test_items_query_normalizes_to_search_for_planner(monkeypatch):
    """플래너가 Items.json 에 query(존재 확인)를 주면 search_items 로 흡수되어 미지원이 되지 않아야 한다."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    calls: list[tuple[str, dict]] = []

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        calls.append((tool_name, dict(arguments or {})))
        return {"success": True, "data": {"found": False}, "modified_files": []}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "아이템 존재 확인",
                "action_type": "query",
                "target_file": "Items.json",
                "target_info": {"name": "만병통치약"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    assert len(calls) == 1
    assert calls[0][0] == "search_items"
    assert calls[0][1].get("searchTerm") == "만병통치약"
    assert result["changes_log"][0]["success"] is True


@pytest.mark.asyncio
async def test_unsupported_structured_step_error_is_standardized():
    """미지원 액션은 executor_v2 dispatch fallback을 시도한 뒤 실패하면 표준 에러를 반환한다."""
    # action_type=delete는 Skills.json에 대해 MCP/레거시 매핑이 없으므로,
    # executor_v2 dispatch fallback을 시도한다. dispatch가 처리하면 성공,
    # 못하면 [UNSUPPORTED_STRUCTURED_STEP] 표준 포맷으로 반환한다.
    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "미지원 액션 테스트",
                "action_type": "delete",
                "target_file": "Skills.json",
                "target_info": {"skill_id": 1},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)
    log = result["changes_log"][0]
    # dispatch fallback이 처리했으면 success, 못했으면 UNSUPPORTED
    if not log["success"]:
        assert "[UNSUPPORTED_STRUCTURED_STEP]" in (log.get("stderr") or "")


@pytest.mark.asyncio
async def test_executor_returns_modified_file_paths_for_reported_changes(monkeypatch):
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        return {"success": True, "data": {"ok": True}, "modified_files": ["Actors.json"]}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "update actor",
                "action_type": "update",
                "target_file": "Actors.json",
                "target_info": {"actor_id": 1, "updates": {"nickname": "Hero"}},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)

    expected_path = str(executor_module._get_data_path(_TEST_GAME_ID) / "Actors.json")
    assert result["modified_file_paths"] == [expected_path]


@pytest.mark.asyncio
async def test_executor_returns_empty_modified_file_paths_for_read_only_query(monkeypatch):
    executor_module = importlib.import_module("agent.graph.nodes.executor")

    async def fake_call_mcp_tool(
        tool_name, arguments, data_path, path_arg_name="targetDir", mcp_server=None
    ):
        return {"success": True, "data": {"id": 3, "name": "Harold"}, "modified_files": []}

    monkeypatch.setattr(executor_module, "is_mcp_enabled", lambda: True)
    monkeypatch.setattr(executor_module, "build_stdio_server_parameters", lambda *a, **k: object())
    monkeypatch.setattr(executor_module, "call_mcp_tool", fake_call_mcp_tool)

    state: AgentState = {
        "execution_plan": [
            {
                "step_id": 1,
                "description": "get actor",
                "action_type": "query",
                "target_file": "Actors.json",
                "target_info": {"actor_id": "3"},
                "depends_on": [],
                "condition": "",
            }
        ],
        "game_id": _TEST_GAME_ID,
        "retry_count": 0,
    }

    result = await executor(state)

    assert result["modified_file_paths"] == []


def test_search_items_mcp_enrichment_sets_exists_from_items_json(tmp_path):
    """MCP가 hits 리스트를 안 줘도 Items.json 로컬 검색으로 exists·item_id를 채운다."""
    import importlib
    import json

    executor_module = importlib.import_module("agent.graph.nodes.executor")

    items = [
        None,
        {"id": 9, "name": "기타"},
        {"id": 10, "name": "매직 워터"},
    ]
    (tmp_path / "Items.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")

    ex, iid = executor_module._items_local_search_by_name(tmp_path, "매직")
    assert ex is True
    assert iid == 10

    r = {"success": True, "data": {"found": False}, "modified_files": []}
    out = executor_module._enrich_mcp_search_tool_result(
        "search_items",
        r,
        data_path=tmp_path,
        norm_args={"searchTerm": "매직 워터"},
    )
    assert out["exists"] is True
    assert out["item_id"] == 10


def test_structured_create_item_sync_writes_items_json(tmp_path):
    """item_id가 있으면 dispatcher 없이 Items.json 슬롯에 스키마 검증 후 기록한다."""
    import importlib
    import json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    data_path = tmp_path / "data"
    data_path.mkdir()
    (data_path / "Items.json").write_text(
        json.dumps([None, None], ensure_ascii=False), encoding="utf-8"
    )

    target_info = {
        "item_id": 1,
        "name": "체력 포션",
        "description": "테스트 설명",
        "iconIndex": 64,
        "price": 0,
        "itypeId": 1,
        "consumable": True,
        "scope": 7,
        "occasion": 0,
        "speed": 0,
        "successRate": 100,
        "repeats": 1,
        "tpGain": 0,
        "hitType": 0,
        "animationId": -1,
        "damage": {
            "type": 3,
            "elementId": 1,
            "formula": "b.mhp",
            "variance": 0,
            "critical": False,
        },
        "effects": [{"code": 11, "dataId": 0, "value1": 0, "value2": 100}],
        "note": "",
    }
    r = executor_module._structured_create_item_sync(data_path, target_info)
    assert r["success"] is True
    arr = json.loads((data_path / "Items.json").read_text(encoding="utf-8"))
    assert arr[1]["name"] == "체력 포션"
    assert arr[1]["id"] == 1
    assert arr[1]["effects"][0]["value2"] == 100


# ──────────────────────────────────────────────────────────────
# _structured_create_item_sync — 실패/엣지 케이스
# ──────────────────────────────────────────────────────────────

_VALID_ITEM_BASE: dict = {
    "name": "포션",
    "description": "테스트",
    "iconIndex": 0,
    "price": 100,
    "itypeId": 1,
    "consumable": True,
    "scope": 7,
    "occasion": 0,
    "speed": 0,
    "successRate": 100,
    "repeats": 1,
    "tpGain": 0,
    "hitType": 0,
    "animationId": -1,
    "damage": {"type": 0, "elementId": 0, "formula": "0", "variance": 20, "critical": False},
    "effects": [],
    "note": "",
}


def _make_items_json(data_path: Path, arr: list | None = None):
    """tmp_path 하위에 Items.json을 준비한다."""
    import json as _json

    data_path.mkdir(parents=True, exist_ok=True)
    content = arr if arr is not None else [None, None]
    (data_path / "Items.json").write_text(
        _json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )


def test_create_item_sync_missing_id(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp)
    r = executor_module._structured_create_item_sync(dp, {"name": "포션"})
    assert r["success"] is False
    assert "item_id" in r["stderr"]


def test_create_item_sync_invalid_id(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp)
    r = executor_module._structured_create_item_sync(dp, {"item_id": "xyz", "name": "포션"})
    assert r["success"] is False
    assert "xyz" in r["stderr"]


def test_create_item_sync_no_file(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    dp.mkdir(parents=True)
    # Items.json 없음
    r = executor_module._structured_create_item_sync(dp, {"item_id": 1, "name": "포션"})
    assert r["success"] is False


def test_create_item_sync_slot_conflict(tmp_path):
    """슬롯에 이미 다른 이름의 아이템이 있으면 충돌 에러."""

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    existing_item = {**_VALID_ITEM_BASE, "id": 1, "name": "기존 포션"}
    _make_items_json(dp, [None, existing_item])
    r = executor_module._structured_create_item_sync(
        dp, {**_VALID_ITEM_BASE, "item_id": 1, "name": "새 포션"}
    )
    assert r["success"] is False
    assert "기존 포션" in r["stderr"]


def test_create_item_sync_schema_bad_scope(tmp_path):
    """scope=99 (max 14) → Pydantic 검증 실패."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp)
    info = {**_VALID_ITEM_BASE, "item_id": 1, "scope": 99}
    r = executor_module._structured_create_item_sync(dp, info)
    assert r["success"] is False
    assert "스키마" in r["stderr"] or "scope" in r["stderr"].lower()


def test_create_item_sync_default_damage(tmp_path):
    """damage 키를 안 주면 기본 damage 블록이 적용된다."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp)
    info = {k: v for k, v in _VALID_ITEM_BASE.items() if k != "damage"}
    info["item_id"] = 1
    r = executor_module._structured_create_item_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Items.json").read_text(encoding="utf-8"))
    assert "damage" in arr[1]
    assert arr[1]["damage"]["formula"] == "0"


def test_create_item_sync_planner_omits_occasion_like_fields(tmp_path):
    """Planner가 Definition 대비 occasion 등 필수 필드를 빼도(또는 null) 성공해야 한다."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp, [None, None, None])
    info = {
        "item_id": 3,
        "item_name": "소화기",
        "description": "화재 진압용 소화기",
        "iconIndex": 1,
        "price": 0,
        "itypeId": 1,
        "consumable": True,
        "scope": 7,
        "speed": 0,
        "successRate": 100,
        "repeats": 1,
        "tpGain": 0,
        "hitType": 0,
        "animationId": -1,
        "damage": {
            "type": 0,
            "elementId": -1,
            "formula": "",
            "variance": 0,
            "critical": False,
        },
        "effects": [],
        "note": "",
        "occasion": None,
    }
    r = executor_module._structured_create_item_sync(dp, info)
    assert r["success"] is True, r.get("stderr")
    arr = _json.loads((dp / "Items.json").read_text(encoding="utf-8"))
    assert arr[3]["name"] == "소화기"
    assert arr[3]["occasion"] == 0


def test_create_item_sync_effects_sanitized(tmp_path):
    """code=11, value1=500, value2=0 → swap 적용 확인."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp)
    info = {
        **_VALID_ITEM_BASE,
        "item_id": 1,
        "effects": [{"code": 11, "dataId": 0, "value1": 500, "value2": 0}],
    }
    r = executor_module._structured_create_item_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Items.json").read_text(encoding="utf-8"))
    eff = arr[1]["effects"][0]
    assert eff["value1"] == 0
    assert eff["value2"] == 500


def test_create_item_sync_skip_keys_filtered(tmp_path):
    """query, searchTerm 등 skip 키는 저장 JSON에 포함되지 않는다."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp)
    info = {
        **_VALID_ITEM_BASE,
        "item_id": 1,
        "query": "포션 검색",
        "searchTerm": "magic",
        "item_name": "무시됨",
    }
    r = executor_module._structured_create_item_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Items.json").read_text(encoding="utf-8"))
    saved = arr[1]
    assert "query" not in saved
    assert "searchTerm" not in saved
    assert "item_name" not in saved


def test_create_item_sync_extends_array(tmp_path):
    """item_id=5인데 배열 길이가 2면 null 패딩 후 기록."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_items_json(dp, [None, None])
    info = {**_VALID_ITEM_BASE, "item_id": 5}
    r = executor_module._structured_create_item_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Items.json").read_text(encoding="utf-8"))
    assert len(arr) >= 6
    assert arr[5]["id"] == 5
    # 중간 슬롯은 None
    assert arr[2] is None
    assert arr[3] is None
    assert arr[4] is None


def test_create_item_sync_corrupt_json(tmp_path):
    """깨진 JSON 파일 → 읽기 실패."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    dp.mkdir(parents=True)
    (dp / "Items.json").write_text("{{not json}}", encoding="utf-8")
    r = executor_module._structured_create_item_sync(dp, {"item_id": 1, "name": "포션"})
    assert r["success"] is False
    assert "읽기 실패" in r["stderr"] or "Items.json" in r["stderr"]


# ──────────────────────────────────────────────────────────────
# _structured_create_enemy_sync — 성공/실패/엣지
# ──────────────────────────────────────────────────────────────

_VALID_ENEMY_BASE: dict = {
    "name": "고블린",
    "battlerName": "Goblin",
    "battlerHue": 0,
    "params": [100, 0, 10, 10, 10, 10, 10, 10],
    "dropItems": [
        {"kind": 0, "dataId": 1, "denominator": 1},
        {"kind": 0, "dataId": 1, "denominator": 1},
        {"kind": 0, "dataId": 1, "denominator": 1},
    ],
    "actions": [
        {"skillId": 1, "rating": 5, "conditionType": 0, "conditionParam1": 0, "conditionParam2": 0}
    ],
    "traits": [],
    "exp": 10,
    "gold": 5,
    "note": "",
}


def _make_enemies_json(data_path: Path, arr: list | None = None):
    import json as _json

    data_path.mkdir(parents=True, exist_ok=True)
    content = arr if arr is not None else [None, None]
    (data_path / "Enemies.json").write_text(
        _json.dumps(content, ensure_ascii=False), encoding="utf-8"
    )


# ── 성공 ──


def test_create_enemy_sync_basic(tmp_path):
    """유효한 enemy로 슬롯 기록 성공."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_enemies_json(dp)
    info = {**_VALID_ENEMY_BASE, "enemy_id": 1}
    r = executor_module._structured_create_enemy_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Enemies.json").read_text(encoding="utf-8"))
    assert arr[1]["name"] == "고블린"
    assert arr[1]["id"] == 1
    assert len(arr[1]["params"]) == 8


def test_create_enemy_sync_extends_array(tmp_path):
    """enemy_id=5, 배열 길이 2 → null 패딩 후 기록."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_enemies_json(dp, [None, None])
    info = {**_VALID_ENEMY_BASE, "enemy_id": 5}
    r = executor_module._structured_create_enemy_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Enemies.json").read_text(encoding="utf-8"))
    assert len(arr) >= 6
    assert arr[5]["id"] == 5
    assert arr[2] is None


def test_create_enemy_sync_overwrites_same_name(tmp_path):
    """같은 이름이면 슬롯 덮어쓰기 허용."""
    import json as _json

    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    existing = {**_VALID_ENEMY_BASE, "id": 1, "name": "고블린", "exp": 5}
    _make_enemies_json(dp, [None, existing])
    info = {**_VALID_ENEMY_BASE, "enemy_id": 1, "name": "고블린", "exp": 99}
    r = executor_module._structured_create_enemy_sync(dp, info)
    assert r["success"] is True
    arr = _json.loads((dp / "Enemies.json").read_text(encoding="utf-8"))
    assert arr[1]["exp"] == 99


# ── 실패 ──


def test_create_enemy_sync_missing_id(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_enemies_json(dp)
    r = executor_module._structured_create_enemy_sync(dp, {"name": "고블린"})
    assert r["success"] is False
    assert "enemy_id" in r["stderr"]


def test_create_enemy_sync_invalid_id(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_enemies_json(dp)
    r = executor_module._structured_create_enemy_sync(dp, {"enemy_id": "abc"})
    assert r["success"] is False
    assert "abc" in r["stderr"]


def test_create_enemy_sync_no_file(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    dp.mkdir(parents=True)
    r = executor_module._structured_create_enemy_sync(dp, {"enemy_id": 1})
    assert r["success"] is False


def test_create_enemy_sync_corrupt_json(tmp_path):
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    dp.mkdir(parents=True)
    (dp / "Enemies.json").write_text("{{bad}}", encoding="utf-8")
    r = executor_module._structured_create_enemy_sync(dp, {"enemy_id": 1})
    assert r["success"] is False


def test_create_enemy_sync_slot_conflict(tmp_path):
    """슬롯에 다른 이름 적이 있으면 충돌 에러."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    existing = {**_VALID_ENEMY_BASE, "id": 1, "name": "고블린"}
    _make_enemies_json(dp, [None, existing])
    info = {**_VALID_ENEMY_BASE, "enemy_id": 1, "name": "드래곤"}
    r = executor_module._structured_create_enemy_sync(dp, info)
    assert r["success"] is False
    assert "고블린" in r["stderr"]


# ── 엣지 ──


def test_create_enemy_sync_empty_array(tmp_path):
    """빈 배열 → 에러."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_enemies_json(dp, [])
    r = executor_module._structured_create_enemy_sync(dp, {"enemy_id": 1})
    assert r["success"] is False
    assert "비어 있지 않은 배열" in r["stderr"]


def test_create_enemy_sync_params_validation_fail(tmp_path):
    """params가 7개이면 스키마 검증 실패."""
    executor_module = importlib.import_module("agent.graph.nodes.executor")
    dp = tmp_path / "data"
    _make_enemies_json(dp)
    info = {**_VALID_ENEMY_BASE, "enemy_id": 1, "params": [100, 0, 10, 10, 10, 10, 10]}
    r = executor_module._structured_create_enemy_sync(dp, info)
    assert r["success"] is False
    assert "스키마" in r["stderr"] or "검증" in r["stderr"]


if __name__ == "__main__":
    # 단독 실행시 테스트
    print("=" * 60)
    print("Executor MVP 단독 테스트 실행")
    print("=" * 60)

    check_game_files()

    # 비동기 테스트 실행
    asyncio.run(test_skill_manager_directly())
    asyncio.run(test_executor_mvp())
