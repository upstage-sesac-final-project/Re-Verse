"""DB 초기화 스크립트.

Usage: uv run python scripts/init_db.py [--seed]
"""

import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.backend.core.config import settings
from app.backend.db.session import init_db


async def main() -> None:
    seed = "--seed" in sys.argv

    if not settings.DATABASE_URL:
        print("DATABASE_URL이 설정되지 않았습니다.")
        print("  예: DATABASE_URL=sqlite+aiosqlite:///./storage/reverse.db")
        sys.exit(1)

    print(f"DATABASE_URL: {settings.DATABASE_URL}")
    print("테이블 생성 중...")
    await init_db()
    print("테이블 생성 완료!")

    # base_game 존재 확인
    base_game = Path(settings.BASE_GAME_PATH).resolve()
    if base_game.exists():
        print(f"base_game 확인: {base_game}")
    else:
        print(f"경고: base_game 경로 없음: {base_game}")

    if seed:
        print("개발용 더미 데이터 생성 중...")
        await _create_seed_data()
        print("시드 데이터 생성 완료!")


async def _create_seed_data() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.backend.core.security import hash_password
    from app.backend.db.session import get_engine
    from app.backend.models.user import User

    engine = get_engine()
    if engine is None:
        return

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as db:
        user = User(
            username="testuser",
            email="test@example.com",
            hashed_password=hash_password("password123"),
        )
        db.add(user)
        await db.commit()
        print(f"  테스트 유저 생성: {user.email}")


if __name__ == "__main__":
    asyncio.run(main())
