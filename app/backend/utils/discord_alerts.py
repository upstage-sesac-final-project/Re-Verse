"""백엔드 예외 시 Discord 웹훅으로 요약 알림 (선택)."""

from __future__ import annotations

import json
import logging
import traceback
from datetime import UTC, datetime
from typing import Any

import httpx
from starlette.requests import Request

from app.backend.core.config import settings

logger = logging.getLogger(__name__)

# Discord embed field value 최대 1024 — 여유 두고 자름
_MAX_FIELD = 950
_MAX_DESC = 3500


def _truncate(text: str, max_len: int) -> str:
    text = (text or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 20] + "\n…(truncated)"


def _extract_user_hint_from_json(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("message", "user_input", "content", "prompt", "text", "query"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    try:
        return json.dumps(data, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(data)


async def extract_request_context(request: Request, exc: BaseException) -> dict[str, str]:
    """요청에서 사용자 입력·경로 등 알림에 넣을 문자열을 모은다."""
    path = request.url.path
    method = request.method
    request_id = getattr(request.state, "request_id", None) or ""
    user_hint = ""

    # GET 쿼리 (테스트·간단 호출)
    try:
        q_msg = request.query_params.get("message") or request.query_params.get("q") or ""
        if isinstance(q_msg, str) and q_msg.strip():
            user_hint = q_msg.strip()
    except Exception:
        pass

    # JSON / raw body (캐시된 body 재사용 가능)
    if not user_hint:
        try:
            body = await request.body()
            if body:
                try:
                    data = json.loads(body)
                    user_hint = _extract_user_hint_from_json(data)
                except (json.JSONDecodeError, UnicodeDecodeError):
                    user_hint = body.decode("utf-8", errors="replace")
        except Exception:
            pass

    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return {
        "path": path,
        "method": method,
        "request_id": str(request_id) if request_id else "",
        "user_hint": user_hint or "N/A",
        "traceback": tb,
        "error_type": type(exc).__name__,
        "error_msg": str(exc),
    }


async def send_discord_error_alert(ctx: dict[str, str]) -> None:
    """DISCORD_WEBHOOK_URL 이 있을 때만 비동기 전송. 실패해도 예외를 삼킨다."""
    url = (settings.DISCORD_WEBHOOK_URL or "").strip()
    if not url:
        return

    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")
    title = f"Re:Verse Backend — {ctx.get('error_type', 'Error')}"
    description = _truncate(ctx.get("error_msg", ""), _MAX_DESC)

    fields = [
        {"name": "Time", "value": ts, "inline": True},
        {"name": "Method", "value": _truncate(ctx.get("method", ""), 100), "inline": True},
        {"name": "Path", "value": _truncate(ctx.get("path", ""), _MAX_FIELD), "inline": False},
    ]
    rid = ctx.get("request_id") or ""
    if rid:
        fields.append({"name": "Request-ID", "value": _truncate(rid, _MAX_FIELD), "inline": False})
    fields.append(
        {
            "name": "User input / body 힌트",
            "value": _truncate(ctx.get("user_hint", "N/A"), _MAX_FIELD),
            "inline": False,
        }
    )
    fields.append(
        {
            "name": "Traceback",
            "value": _truncate(ctx.get("traceback", ""), _MAX_FIELD),
            "inline": False,
        }
    )

    payload: dict[str, Any] = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": 15158332,
                "fields": fields,
            }
        ]
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0)) as client:
            r = await client.post(url, json=payload)
            if 200 <= r.status_code < 300:
                logger.info("Discord webhook 전송 성공 (HTTP %s)", r.status_code)
                return
            logger.warning(
                "Discord webhook 비정상 응답 HTTP %s: %s",
                r.status_code,
                (r.text or "")[:500],
            )
    except Exception:
        logger.error("Discord webhook 전송 실패 (네트워크/SSL 등)", exc_info=True)
