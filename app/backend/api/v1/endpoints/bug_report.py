"""버그 리포트 엔드포인트 — Discord webhook으로 전달."""

import logging
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.backend.core.security import get_current_user
from app.backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_CONTENT_LEN = 4000


class BugReportPayload(BaseModel):
    content: str = Field(..., min_length=1, max_length=_MAX_CONTENT_LEN)


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def submit_bug_report(
    payload: BugReportPayload,
    current_user: User = Depends(get_current_user),
):
    """로그인 사용자의 버그 리포트를 Discord webhook으로 전송한다."""
    webhook_url = os.getenv("DISCORD_BUG_WEBHOOK_URL", "").strip()
    if not webhook_url:
        logger.error("[BugReport] DISCORD_BUG_WEBHOOK_URL 미설정")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="버그 리포트 채널이 설정되지 않았습니다.",
        )

    content = payload.content.strip()
    embed = {
        "title": "🐛 새 버그 리포트",
        "description": content[:_MAX_CONTENT_LEN],
        "color": 0xE74C3C,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [
            {"name": "사용자", "value": current_user.username or "(unknown)", "inline": True},
            {"name": "이메일", "value": current_user.email or "(unknown)", "inline": True},
            {"name": "User ID", "value": str(current_user.id), "inline": True},
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(webhook_url, json={"embeds": [embed]})
            res.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("[BugReport] Discord webhook 전송 실패: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="버그 리포트 전송에 실패했습니다.",
        ) from exc

    logger.info("[BugReport] 전송 완료 | user_id=%s len=%d", current_user.id, len(content))
    return None
