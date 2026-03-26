"""Executor MVP 테스트

기본적인 동작 확인용 테스트들
"""

import asyncio
import logging
import uuid
from pathlib import Path

from agent.graph.nodes.executor import executor
from agent.graph.state import AgentState
from app.backend.services.json_modify_tools.managers.actor_manager import ActorManager
from app.backend.services.json_modify_tools.managers.skill_manager import SkillManager

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_executor_mvp():
    """MVP 기본 동작 테스트"""

    print("🧪 Executor MVP 테스트 시작")

    # ── 테스트 1: 기본 스킬 추가 ─────────────────────────────
    test_state = {
        "execution_plan": [
            {"task": "파이어볼 스킬 추가해줘", "description": "새로운 화염 공격 스킬"}
        ],
        "game_id": "game_001",
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
        "game_id": "game_001",
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
        "game_id": "game_001",
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


async def test_structured_execution_plan_actors():
    """3단계 구조화 execution_plan: Actors.json query → 조건부 create."""
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
        "game_id": "game_001",
        "retry_count": 0,
    }

    result = await executor(state)
    logs = result.get("changes_log", [])
    assert len(logs) >= 2
    q = next((x for x in logs if x.get("tool_name") == "structured_actors_query"), None)
    c = next((x for x in logs if x.get("tool_name") == "structured_actors_create"), None)
    assert q is not None and q.get("success") is True
    assert q.get("exists") is False
    assert c is not None and c.get("success") is True

    data_path = Path(__file__).resolve().parents[2] / "storage" / "games" / "game_001" / "data"
    mgr = ActorManager(data_path, "test_verify")
    verify = await mgr.execute("query", actor_name=unique_name)
    assert verify.get("exists") is True

    result2 = await executor(state)
    logs2 = result2.get("changes_log", [])
    skipped = [x for x in logs2 if x.get("skipped")]
    assert any("존재" in (x.get("skip_reason") or "") for x in skipped)


async def test_skill_manager_directly():
    """SkillManager 직접 테스트"""

    print("\n🛠️ SkillManager 직접 테스트")

    data_path = Path(__file__).resolve().parents[2] / "storage" / "games" / "game_001" / "data"

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

    data_path = Path(__file__).resolve().parents[2] / "storage" / "games" / "game_001" / "data"
    required_files = ["Skills.json", "Enemies.json", "Items.json"]

    for file_name in required_files:
        file_path = data_path / file_name
        if file_path.exists():
            size = file_path.stat().st_size
            print(f"✅ {file_name}: {size} bytes")
        else:
            print(f"❌ {file_name}: 파일 없음")


if __name__ == "__main__":
    # 단독 실행시 테스트
    print("=" * 60)
    print("🚀 Executor MVP 단독 테스트 실행")
    print("=" * 60)

    check_game_files()

    # 비동기 테스트 실행
    asyncio.run(test_skill_manager_directly())
    asyncio.run(test_executor_mvp())
