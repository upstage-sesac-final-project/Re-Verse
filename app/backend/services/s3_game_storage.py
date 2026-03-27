"""S3 ↔ 로컬 디스크 게임 폴더 동기화 (프로덕션용).

EC2 IAM 역할로 boto3가 자격 증명을 받습니다(ACCESS_KEY 불필요).
버킷 키 규칙: {S3_PREFIX}{game_id}/... 예: games/game_001/data/Actors.json
"""

from __future__ import annotations

import logging
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.backend.core.config import settings

logger = logging.getLogger(__name__)


def _s3_client():
    return boto3.client("s3", region_name=settings.AWS_REGION)


def _game_s3_prefix(game_id: str) -> str:
    """games/game_001/ 형태 (끝에 /)."""
    base = settings.S3_PREFIX.strip("/")
    return f"{base}/{game_id}/"


def sync_game_from_s3(game_id: str) -> None:
    """S3의 games/{game_id}/ 아래 객체를 STORAGE_PATH/{game_id}/ 로 내려받는다."""
    if settings.STORAGE_BACKEND != "s3":
        return

    client = _s3_client()
    bucket = settings.S3_BUCKET_NAME
    prefix = _game_s3_prefix(game_id)
    local_root = Path(settings.STORAGE_PATH).resolve() / game_id
    local_root.mkdir(parents=True, exist_ok=True)

    paginator = client.get_paginator("list_objects_v2")
    downloaded = 0
    try:
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                rel = key[len(prefix) :].lstrip("/")
                if not rel:
                    continue
                dest = local_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                client.download_file(bucket, key, str(dest))
                downloaded += 1
    except ClientError as e:
        logger.error("S3 download 실패 game_id=%s: %s", game_id, e)
        raise

    logger.info("S3 → 로컬 동기화 완료 game_id=%s files=%d", game_id, downloaded)


def sync_game_to_s3(game_id: str) -> None:
    """STORAGE_PATH/{game_id}/ 전체를 S3 prefix games/{game_id}/ 로 업로드한다."""
    if settings.STORAGE_BACKEND != "s3":
        return

    local_root = Path(settings.STORAGE_PATH).resolve() / game_id
    if not local_root.is_dir():
        logger.warning("업로드할 로컬 게임 폴더 없음: %s", local_root)
        return

    client = _s3_client()
    bucket = settings.S3_BUCKET_NAME
    prefix = _game_s3_prefix(game_id)
    uploaded = 0
    try:
        for path in local_root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(local_root)
            key = f"{prefix}{rel.as_posix()}"
            client.upload_file(str(path), bucket, key)
            uploaded += 1
    except ClientError as e:
        logger.error("S3 upload 실패 game_id=%s: %s", game_id, e)
        raise

    logger.info("로컬 → S3 업로드 완료 game_id=%s files=%d", game_id, uploaded)


def check_s3_bucket_access() -> tuple[bool, str]:
    """헬스체크용: ListBucket 또는 HeadBucket 수준으로 접근 가능 여부."""
    if settings.STORAGE_BACKEND != "s3":
        return True, "skipped (STORAGE_BACKEND=local)"
    try:
        _s3_client().head_bucket(Bucket=settings.S3_BUCKET_NAME)
        return True, "ok"
    except ClientError as e:
        return False, str(e)
