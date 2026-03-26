"""Executor MVP 사용 예제

4단계 Executor를 실제로 사용하는 방법을 보여주는 예제들
"""

import asyncio
import json
from pathlib import Path

from agent.graph.nodes.executor import executor


async def example_1_skill_creation():
    """예제 1: 새로운 스킬 생성"""

    print("🎯 예제 1: 파이어볼 스킬 생성")

    # 3단계(Planner)에서 넘어올 execution_plan 시뮬레이션
    state = {
        "execution_plan": [
            {
                "action": "create_skill",
                "target": "파이어볼",
                "properties": {"damage": "높음", "mana_cost": 50, "range": "단일"},
                "description": "강력한 화염 공격 스킬을 만들어주세요",
            }
        ],
        "game_id": "game_001",
        "retry_count": 0,
    }

    print("📥 입력 (3단계에서 온 수도코드):")
    print(json.dumps(state["execution_plan"], ensure_ascii=False, indent=2))

    # Executor 실행
    result = await executor(state)

    print("\n📤 출력 (5단계로 보낼 결과):")
    print(f"   - 백업 파일: {len(result.get('backup_paths', {}))}개")
    print(f"   - 변경 로그: {len(result.get('changes_log', []))}개")

    # 성공한 작업 출력
    for log in result.get("changes_log", []):
        status = "✅" if log.get("success") else "❌"
        print(f"   {status} {log.get('tool_name')}: {log.get('stdout', log.get('error'))}")


async def example_2_monster_and_level():
    """예제 2: 몬스터 추가 + 레벨 설정 (복수 작업)"""

    print("\n🎯 예제 2: 슬라임 추가 + 레벨 99 설정")

    state = {
        "execution_plan": [
            {"action": "add_monster", "target": "킹 슬라임", "stats": {"hp": 9999, "attack": 500}},
            {"action": "set_level", "target": "주인공", "level": 99},
        ],
        "game_id": "game_001",
        "retry_count": 0,
    }

    print("📥 입력 (복수 작업):")
    for i, plan in enumerate(state["execution_plan"]):
        print(f"   {i + 1}. {plan.get('action')}: {plan.get('target')}")

    result = await executor(state)

    print("\n📤 출력:")
    for i, log in enumerate(result.get("changes_log", [])):
        status = "✅" if log.get("success") else "❌"
        print(f"   단계 {i + 1} {status}: {log.get('stdout', log.get('error'))}")


async def example_3_validation_failure_simulation():
    """예제 3: 검증 실패 → 재시도 시뮬레이션"""

    print("\n🎯 예제 3: 검증 실패 후 재시도")

    # 1차 실행 (실패 예정)
    state = {
        "execution_plan": [{"task": "잘못된 명령어 테스트"}],
        "game_id": "game_001",
        "retry_count": 0,
    }

    print("📥 1차 실행:")
    result1 = await executor(state)

    # 2차 재시도 (validation_result에 에러 포함)
    retry_state = {
        **state,
        "retry_count": 1,
        "validation_result": {"passed": False, "errors": ["이전 번역에서 키워드 인식 실패"]},
    }

    print("📥 2차 재시도 (에러 컨텍스트 포함):")
    result2 = await executor(retry_state)

    print("📤 재시도 결과:")
    print(f"   - 1차: {len(result1.get('changes_log', []))}개 로그")
    print(f"   - 2차: {len(result2.get('changes_log', []))}개 로그")


async def example_4_backup_and_rollback():
    """예제 4: 백업 및 롤백 시스템 테스트"""

    print("\n🎯 예제 4: 백업/롤백 시스템")

    from agent.graph.nodes.executor import _get_data_path, execute_rollback

    # 테스트 백업 경로
    data_path = _get_data_path("game_001")
    backup_paths = {"Skills.json": str(data_path.parent / "backup" / "Skills.json.test.bak")}

    print(f"📂 데이터 경로: {data_path}")
    print(f"💾 백업 경로: {backup_paths}")

    # 롤백 테스트 (실제 파일 없어도 에러 처리 확인)
    rollback_results = execute_rollback(backup_paths, data_path)

    print("🔄 롤백 결과:")
    for result_msg in rollback_results:
        print(f"   - {result_msg}")


def check_storage_structure():
    """저장소 구조 확인"""

    print("\n📁 저장소 구조 확인")

    root = Path(__file__).parents[3]  # Re-Verse/
    storage_path = root / "storage" / "games" / "game_001"

    print(f"프로젝트 루트: {root}")
    print(f"저장소 경로: {storage_path}")

    if storage_path.exists():
        print("✅ 저장소 폴더 존재")

        data_path = storage_path / "data"
        if data_path.exists():
            print(f"✅ 데이터 폴더 존재: {data_path}")

            # JSON 파일들 체크
            json_files = list(data_path.glob("*.json"))
            print(f"📄 JSON 파일: {len(json_files)}개")

            for json_file in json_files[:5]:  # 처음 5개만
                size = json_file.stat().st_size
                print(f"   - {json_file.name}: {size} bytes")
        else:
            print("❌ 데이터 폴더 없음")
    else:
        print("❌ 저장소 폴더 없음")


async def main():
    """모든 예제 실행"""

    print("🚀 Executor MVP 전체 예제 실행")
    print("=" * 60)

    # 구조 체크
    check_storage_structure()

    # 예제들 순차 실행
    await example_1_skill_creation()
    await example_2_monster_and_level()
    await example_3_validation_failure_simulation()
    await example_4_backup_and_rollback()

    print("\n🎉 모든 예제 완료!")


if __name__ == "__main__":
    asyncio.run(main())
