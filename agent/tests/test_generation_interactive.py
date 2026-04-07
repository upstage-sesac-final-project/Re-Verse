"""Full Generation 인터랙티브 테스트.

DB에 프로젝트를 먼저 등록한 뒤 에이전트를 실행하므로,
localhost:3000 프론트엔드에서 생성된 게임을 바로 확인할 수 있습니다.

실행:
    uv run python -m agent.tests.test_generation_interactive
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from agent.graph.state import AgentState
from agent.graph.workflow import graph

load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("GenerationTest")


# ── DB 세션 헬퍼 ──────────────────────────────────────────────


@asynccontextmanager
async def _db_session():
    """테스트용 DB 세션 컨텍스트 매니저."""
    from app.backend.db.session import get_engine

    get_engine()  # 지연 초기화 트리거

    # get_engine() 호출 후 재임포트해야 _async_session이 채워진 값을 가져옴
    import app.backend.db.session as _sess_mod

    sf = _sess_mod._async_session
    if sf is None:
        raise RuntimeError("DB 세션 팩토리 초기화 실패 — DATABASE_URL을 확인하세요.")

    async with sf() as session:
        yield session


async def _pick_user() -> int | None:
    """DB에서 유저 목록을 출력하고 선택하게 한다."""
    from sqlalchemy import select

    from app.backend.models.user import User

    try:
        async with _db_session() as db:
            result = await db.execute(select(User).order_by(User.id))
            users = result.scalars().all()
    except Exception as e:
        print(f"  [오류] 유저 목록 조회 실패: {e}")
        return None

    if not users:
        print("  [오류] DB에 유저가 없습니다. 먼저 회원가입 하세요.")
        return None

    print("\n  [DB 유저 목록]")
    for u in users:
        admin_tag = " (admin)" if u.is_admin else ""
        print(f"    {u.id}: {u.username} <{u.email}>{admin_tag}")

    uid_input = input("\n  사용할 유저 ID 입력: ").strip()
    if not uid_input.isdigit():
        return None
    chosen = int(uid_input)
    if not any(u.id == chosen for u in users):
        print(f"  [오류] ID {chosen} 는 목록에 없습니다.")
        return None
    return chosen


async def _register_project(user_id: int, title: str) -> tuple[str, int]:
    """DB에 Project 레코드를 생성하고 (game_id, project_id)를 반환."""
    from app.backend.services.game_service import game_service

    async with _db_session() as db:
        project = await game_service.create_project(
            user_id=user_id,
            name=title,
            description="인터랙티브 테스트로 생성",
            db=db,
        )
        return project.game_id, project.id


# ── 메인 테스트 루프 ──────────────────────────────────────────


async def run_interactive_test():
    print("\n" + "=" * 60)
    print("Re:Verse Full Generation 인터랙티브 테스트")
    print("생성된 게임은 localhost:3000 에서 확인 가능합니다.")
    print("종료: 'exit' 또는 'quit'")
    print("=" * 60 + "\n")

    # DB에서 유저 목록 조회 후 선택
    user_id = await _pick_user()
    if user_id is None:
        print("유저를 선택하지 못했습니다. 종료합니다.")
        return
    print(f"  → user_id={user_id} 로 테스트합니다.\n")

    while True:
        user_input = input("사용자 입력: ").strip()

        if user_input.lower() in ["exit", "quit"]:
            print("테스트를 종료합니다.")
            break
        if not user_input:
            continue

        # 1. DB에 프로젝트 등록 (game_id 확보)
        try:
            game_id, project_id = await _register_project(
                user_id=user_id,
                title=user_input[:50],  # 쿼리 앞 50자를 프로젝트 이름으로 사용
            )
            print(f"\n  [DB] 프로젝트 등록 완료 | project_id={project_id}, game_id={game_id}")
        except Exception as e:
            logger.error("프로젝트 DB 등록 실패: %s", e, exc_info=True)
            print(f"\n  [오류] DB 등록 실패: {e}")
            print("  → 백엔드 서버가 실행 중인지, DATABASE_URL이 올바른지 확인하세요.")
            continue

        # 2. AgentState 구성 (DB에서 받은 game_id 사용)
        state = AgentState(
            user_input=user_input,
            game_id=game_id,
            conversation_history=[],
            changes_log=[],
            tool_results=[],
        )

        print("  파이프라인 실행 중...\n")

        try:
            # 3. 메인 그래프 실행
            final_state = await graph.ainvoke(state)

            intent = final_state.get("intent", "분류 실패")
            response = final_state.get("final_response", "응답 생성 실패")

            print("-" * 40)
            print(f"  의도: {intent}")
            print(f"  응답:\n{response}")
            print("-" * 40)

            # 4. Full Generation 결과 파일 확인
            if intent == "전체_게임_생성":
                save_path = os.path.join("storage", "games", game_id, "data")
                if os.path.exists(save_path):
                    files = os.listdir(save_path)
                    print(f"  [파일] {len(files)}개 생성: {', '.join(sorted(files)[:8])}...")
                    print(
                        f"  [확인] localhost:3000 에서 project_id={project_id} 게임을 확인하세요."
                    )
                else:
                    print("  [주의] 파일 저장 경로를 찾을 수 없습니다.")

        except Exception as e:
            logger.error("파이프라인 실행 오류: %s", e, exc_info=True)
            print(f"\n  [오류] {e}")

        print()


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_test())
    except KeyboardInterrupt:
        print("\n중단되었습니다.")
