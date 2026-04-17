"""
EC2 상태 변경 이벤트를 Discord로 전송하는 Lambda 핸들러.

권장 연결:
EventBridge (EC2 state-change) -> Lambda -> Discord webhook

환경 변수:
- DISCORD_INFRA_WEBHOOK_URL (권장, 기존 인프라 알림과 이름 통일)
- DISCORD_WEBHOOK_URL (fallback)
- TARGET_INSTANCE_ID (선택: 특정 EC2만 알림)
- TIMEZONE (선택: 기본 Asia/Seoul)
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import boto3

ec2 = boto3.client("ec2")


def _webhook_url() -> str:
    return (
        os.getenv("DISCORD_INFRA_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL") or ""
    ).strip()


def _target_instance_id() -> str:
    return (os.getenv("TARGET_INSTANCE_ID") or "").strip()


def _timezone() -> str:
    return (os.getenv("TIMEZONE") or "Asia/Seoul").strip()


def _instance_name(instance_id: str) -> str:
    try:
        resp = ec2.describe_instances(InstanceIds=[instance_id])
        reservations = resp.get("Reservations", [])
        if not reservations:
            return "unknown"
        instance = reservations[0]["Instances"][0]
        for tag in instance.get("Tags", []):
            if tag.get("Key") == "Name":
                return str(tag.get("Value") or "unnamed")
        return "unnamed"
    except Exception:
        return "unknown"


def _to_local_time(iso_utc: str) -> str:
    # EventBridge time 예: 2026-04-17T03:10:27Z
    dt_utc = datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(UTC)
    try:
        dt_local = dt_utc.astimezone(ZoneInfo(_timezone()))
    except Exception:
        dt_local = dt_utc
    return dt_local.strftime("%Y-%m-%d %H:%M:%S %Z")


def _send_discord(content: str) -> None:
    url = _webhook_url()
    if not url:
        raise RuntimeError("DISCORD_INFRA_WEBHOOK_URL (or DISCORD_WEBHOOK_URL) is not set")

    payload = {"content": content}
    req = urllib.request.Request(
        url=url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        if not (200 <= res.status < 300):
            raise RuntimeError(f"Discord webhook failed: HTTP {res.status}")


def lambda_handler(event, context):
    detail = event.get("detail", {})
    instance_id = str(detail.get("instance-id", "unknown"))
    state = str(detail.get("state", "unknown")).lower()

    target_id = _target_instance_id()
    if target_id and instance_id != target_id:
        return {"ok": True, "skipped": "not target instance"}

    instance_name = _instance_name(instance_id)
    local_time = _to_local_time(str(event.get("time", datetime.now(UTC).isoformat())))
    region = str(event.get("region", "unknown"))
    account = str(event.get("account", "unknown"))

    emoji = "🔴" if state in {"stopping", "stopped", "terminated"} else "🟢"

    message = (
        f"{emoji} **[Re:Verse EC2 상태 변경]**\n"
        f"- 서버 이름: `{instance_name}`\n"
        f"- 인스턴스 ID: `{instance_id}`\n"
        f"- 상태: **`{state.upper()}`**\n"
        f"- 시간: `{local_time}`\n"
        f"- 리전: `{region}` / 계정: `{account}`"
    )

    _send_discord(message)
    return {"ok": True, "instance_id": instance_id, "state": state}
