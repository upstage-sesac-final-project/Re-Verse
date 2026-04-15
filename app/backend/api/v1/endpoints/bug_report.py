"""버그 리포트 엔드포인트 — Discord webhook으로 전달."""

import io
import json
import logging
import os
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image

from app.backend.core.security import get_current_user
from app.backend.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()

_MAX_CONTENT_LEN = 4000
_DISCORD_FILE_LIMIT = 10 * 1024 * 1024  # 10MB
_RESIZE_THRESHOLD = 5 * 1024 * 1024  # 5MB 초과 시 리사이즈
_MAX_LONG_SIDE = 1920
_JPEG_QUALITY = 80
_ALLOWED_MIME_PREFIX = "image/"


def _maybe_resize(raw: bytes, mime: str) -> tuple[bytes, str, str]:
    """필요 시 이미지를 리사이즈/재인코딩한다.

    Returns: (data, content_type, filename_ext)
    """
    if len(raw) <= _RESIZE_THRESHOLD:
        ext = "png" if "png" in mime else "jpg"
        return raw, mime, ext

    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception as exc:
        logger.warning("[BugReport] 이미지 디코드 실패, 원본 전송 시도: %s", exc)
        ext = "png" if "png" in mime else "jpg"
        return raw, mime, ext

    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    long_side = max(img.size)
    if long_side > _MAX_LONG_SIDE:
        scale = _MAX_LONG_SIDE / long_side
        new_size = (int(img.size[0] * scale), int(img.size[1] * scale))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
    return buf.getvalue(), "image/jpeg", "jpg"


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def submit_bug_report(
    content: str = Form(..., min_length=1, max_length=_MAX_CONTENT_LEN),
    image: UploadFile | None = File(None),
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

    text = content.strip()
    embed = {
        "title": "🐛 새 버그 리포트",
        "description": text[:_MAX_CONTENT_LEN],
        "color": 0xE74C3C,
        "timestamp": datetime.utcnow().isoformat(),
        "fields": [
            {"name": "사용자", "value": current_user.username or "(unknown)", "inline": True},
            {"name": "이메일", "value": current_user.email or "(unknown)", "inline": True},
            {"name": "User ID", "value": str(current_user.id), "inline": True},
        ],
    }

    files = None
    if image is not None and image.filename:
        if not (image.content_type or "").startswith(_ALLOWED_MIME_PREFIX):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="이미지 파일만 첨부할 수 있습니다.",
            )
        raw = await image.read()
        data, mime, ext = _maybe_resize(raw, image.content_type or "image/png")
        if len(data) > _DISCORD_FILE_LIMIT:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="첨부 이미지가 너무 큽니다.",
            )
        filename = f"bug_{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}"
        embed["image"] = {"url": f"attachment://{filename}"}
        files = {"files[0]": (filename, data, mime)}
        logger.info("[BugReport] 이미지 첨부 | original=%dB final=%dB", len(raw), len(data))

    payload = {"embeds": [embed]}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            if files:
                res = await client.post(
                    webhook_url,
                    data={"payload_json": json.dumps(payload)},
                    files=files,
                )
            else:
                res = await client.post(webhook_url, json=payload)
            res.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("[BugReport] Discord webhook 전송 실패: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="버그 리포트 전송에 실패했습니다.",
        ) from exc

    logger.info("[BugReport] 전송 완료 | user_id=%s len=%d", current_user.id, len(text))
    return None
