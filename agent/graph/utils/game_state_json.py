"""Executor가 넘긴 스냅샷: 디스크 경로(str) 또는 레거시 인메모리 dict/list."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_snapshot_payload(value: Any) -> Any:
    """경로 문자열이면 해당 JSON 파일을 읽고, 아니면 값 그대로 반환(레거시 호환).

    4단계는 `current_game_state` / `modified_game_state`에 **파일 절대 경로**를 넣는다.
    2·5단계 등에서 동일 유틸로 내용을 연다.
    """
    if isinstance(value, str) and value.strip():
        path = Path(value)
        if not path.is_file():
            logger.warning("스냅샷 파일 없음: %s", value)
            return {"_snapshot_error": f"file not found: {value}"}
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except OSError as e:
            logger.warning("스냅샷 읽기 실패: %s - %s", value, e)
            return {"_snapshot_error": str(e)}
        except json.JSONDecodeError as e:
            logger.warning("스냅샷 JSON 파싱 실패: %s - %s", value, e)
            return {"_snapshot_error": str(e)}
    return value
