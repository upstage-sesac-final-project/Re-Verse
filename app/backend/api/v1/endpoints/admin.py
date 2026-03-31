"""Admin 모니터링 & 통계 엔드포인트."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.config import settings
from app.backend.core.security import get_admin_user
from app.backend.db.session import check_database_connection, get_db
from app.backend.models.game import ConversationLog, Project
from app.backend.models.refresh_token import RefreshToken
from app.backend.models.user import User

router = APIRouter(dependencies=[Depends(get_admin_user)])

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")


def _date_group(col, period: str):
    """SQLite / PostgreSQL 양쪽 호환 날짜 그룹핑."""
    if period == "monthly":
        if _is_sqlite:
            return func.strftime("%Y-%m", col).label("date")
        return func.to_char(col, "YYYY-MM").label("date")
    else:
        if _is_sqlite:
            return func.strftime("%Y-%m-%d", col).label("date")
        return func.to_char(col, "YYYY-MM-DD").label("date")


@router.get("/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)):
    """전체 요약 통계."""
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    total_projects = (await db.execute(select(func.count()).select_from(Project))).scalar() or 0

    conv_stats = (
        await db.execute(
            select(
                func.count().label("total"),
                func.avg(case((ConversationLog.success.is_(True), 1.0), else_=0.0)).label(
                    "success_rate"
                ),
                func.avg(ConversationLog.processing_time).label("avg_time"),
            ).select_from(ConversationLog)
        )
    ).one()

    return {
        "total_users": total_users,
        "total_projects": total_projects,
        "total_conversations": conv_stats.total or 0,
        "success_rate": round(float(conv_stats.success_rate or 0), 3),
        "avg_processing_time": round(float(conv_stats.avg_time or 0), 2),
    }


@router.get("/stats/signups")
async def stats_signups(
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """신규 유저 가입 트렌드."""
    since = datetime.now(UTC) - timedelta(days=days)
    date_col = _date_group(User.created_at, period)

    rows = (
        await db.execute(
            select(date_col, func.count().label("count"))
            .where(User.created_at >= since)
            .group_by("date")
            .order_by("date")
        )
    ).all()

    return [{"date": str(r.date), "count": r.count} for r in rows]


@router.get("/stats/logins")
async def stats_logins(
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """로그인 트렌드 (RefreshToken 생성 기준)."""
    since = datetime.now(UTC) - timedelta(days=days)
    date_col = _date_group(RefreshToken.created_at, period)

    rows = (
        await db.execute(
            select(date_col, func.count(func.distinct(RefreshToken.user_id)).label("count"))
            .where(RefreshToken.created_at >= since)
            .group_by("date")
            .order_by("date")
        )
    ).all()

    return [{"date": str(r.date), "count": r.count} for r in rows]


@router.get("/stats/usage")
async def stats_usage(
    period: str = Query("daily", pattern="^(daily|monthly)$"),
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
):
    """API 사용량 트렌드 (대화 수 기준)."""
    since = datetime.now(UTC) - timedelta(days=days)
    date_col = _date_group(ConversationLog.timestamp, period)

    rows = (
        await db.execute(
            select(
                date_col,
                func.count().label("total"),
                func.sum(case((ConversationLog.success.is_(True), 1), else_=0)).label("success"),
                func.sum(case((ConversationLog.success.is_(False), 1), else_=0)).label("failed"),
            )
            .where(ConversationLog.timestamp >= since)
            .group_by("date")
            .order_by("date")
        )
    ).all()

    return [
        {
            "date": str(r.date),
            "total": r.total,
            "success": int(r.success or 0),
            "failed": int(r.failed or 0),
        }
        for r in rows
    ]


@router.get("/stats/intents")
async def stats_intents(db: AsyncSession = Depends(get_db)):
    """Intent 분포."""
    rows = (
        await db.execute(
            select(ConversationLog.intent, func.count().label("count"))
            .where(ConversationLog.intent.isnot(None))
            .group_by(ConversationLog.intent)
            .order_by(func.count().desc())
        )
    ).all()

    return [{"intent": r.intent, "count": r.count} for r in rows]


@router.get("/health")
async def admin_health(db: AsyncSession = Depends(get_db)):
    """시스템 헬스 체크."""
    db_ok, db_detail = await check_database_connection()

    s3_result = {"ok": False, "detail": "S3 체크 미실행"}
    try:
        import asyncio

        from app.backend.services.s3_game_storage import check_s3_bucket_access

        s3_ok, s3_detail = await asyncio.to_thread(check_s3_bucket_access)
        s3_result = {"ok": s3_ok, "detail": s3_detail}
    except Exception as e:
        s3_result = {"ok": False, "detail": str(e)}

    return {
        "db": {"ok": db_ok, "detail": db_detail},
        "s3": s3_result,
    }
