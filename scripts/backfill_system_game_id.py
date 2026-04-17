"""기존 프로젝트 System.json 의 advanced.gameId 를 프로젝트별 고유값으로 백필.

base_game 의 고정 gameId(72894844) 를 그대로 상속한 기존 프로젝트들은 같은 origin
(`/game/<id>/`) 에서 localStorage 키(`rmmzsave.<gameId>.*`)가 충돌해 다른 게임의
세이브로 "이어하기" 가 활성화된다. 이 스크립트는 각 프로젝트에 1..2^31-1 범위의
고유 난수를 주입한다.

사용:
    uv run python scripts/backfill_system_game_id.py            # dry-run (변경 없음)
    uv run python scripts/backfill_system_game_id.py --apply    # 실제 적용
    uv run python scripts/backfill_system_game_id.py --apply --force
        # BASE_GAME_ID 가 아니어도 전부 덮어쓰기 (기존에 임의값이 있어도 초기화)
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backend.core.config import settings  # noqa: E402

BASE_GAME_ID = 72894844


def _new_game_id() -> int:
    return secrets.randbelow(2**31 - 1) + 1


def _patch_system(data: dict, force: bool) -> tuple[bool, int | None]:
    current = data.get("advanced", {}).get("gameId")
    if current != BASE_GAME_ID and not force:
        return False, current
    new_id = _new_game_id()
    data.setdefault("advanced", {})["gameId"] = new_id
    return True, new_id


def _iter_local_projects() -> list[Path]:
    root = Path(settings.STORAGE_PATH).resolve()
    if not root.exists():
        return []
    return [
        p
        for p in root.iterdir()
        if p.is_dir() and p.name != "base_game" and (p / "data" / "System.json").exists()
    ]


def _run_local(apply: bool, force: bool) -> None:
    projects = _iter_local_projects()
    print(f"[local] 발견된 프로젝트: {len(projects)}개 (base_game 제외)")
    patched = 0
    skipped = 0
    for proj in projects:
        sys_path = proj / "data" / "System.json"
        data = json.loads(sys_path.read_text(encoding="utf-8"))
        changed, new_id = _patch_system(data, force=force)
        if not changed:
            skipped += 1
            print(f"  - SKIP {proj.name}: gameId={new_id} (이미 고유 또는 force=False)")
            continue
        if apply:
            sys_path.write_text(
                json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
            )
        patched += 1
        print(f"  - {'APPLY' if apply else 'DRY'} {proj.name}: gameId → {new_id}")
    print(f"[local] 완료: 갱신={patched}, 건너뜀={skipped}, apply={apply}")


def _run_s3(apply: bool, force: bool) -> None:
    client = boto3.client("s3", region_name=settings.AWS_REGION)
    bucket = settings.S3_BUCKET_NAME
    prefix = settings.S3_PREFIX.strip("/")
    paginator = client.get_paginator("list_objects_v2")

    game_ids: set[str] = set()
    for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/", Delimiter="/"):
        for cp in page.get("CommonPrefixes", []) or []:
            name = cp["Prefix"][len(prefix) + 1 :].rstrip("/")
            if name and name != "base_game":
                game_ids.add(name)

    print(f"[s3] 발견된 프로젝트: {len(game_ids)}개")
    patched = 0
    skipped = 0
    for gid in sorted(game_ids):
        key = f"{prefix}/{gid}/data/System.json"
        try:
            obj = client.get_object(Bucket=bucket, Key=key)
        except ClientError as e:
            print(f"  - MISS {gid}: System.json 없음 ({e})")
            continue
        data = json.loads(obj["Body"].read().decode("utf-8"))
        changed, new_id = _patch_system(data, force=force)
        if not changed:
            skipped += 1
            print(f"  - SKIP {gid}: gameId={new_id}")
            continue
        if apply:
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
                ContentType="application/json",
            )
        patched += 1
        print(f"  - {'APPLY' if apply else 'DRY'} {gid}: gameId → {new_id}")
    print(f"[s3] 완료: 갱신={patched}, 건너뜀={skipped}, apply={apply}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="실제로 파일을 수정 (기본: dry-run)")
    ap.add_argument("--force", action="store_true", help="BASE_GAME_ID 가 아니어도 강제로 덮어쓰기")
    args = ap.parse_args()

    backend = (settings.STORAGE_BACKEND or "local").lower()
    print(f"STORAGE_BACKEND={backend}, apply={args.apply}, force={args.force}")
    if backend == "s3":
        _run_s3(apply=args.apply, force=args.force)
    else:
        _run_local(apply=args.apply, force=args.force)


if __name__ == "__main__":
    main()
