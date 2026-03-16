"""
JSON Modify Tools Dispatcher
사용자 입력을 파싱해 edit_enemies / edit_items / edit_map_villager 를 실행하는 함수 모음.
라우팅(의도 분류)은 llm_service.py 의 if/else 에서 담당하므로 여기서는 다루지 않는다.

사용 예시
---------
from app.backend.services.json_modify_tools.dispatcher import (
    run_enemies, run_items, run_map_villager
)

result = run_enemies("까마귀 적을 추가해줘")
result = run_items("독약 아이템 추가해줘")
result = run_map_villager("맵 9번에 빌리저 추가해줘")
result = run_levels("레벨 50으로 설정해줘")
result = run_skills("최후의일격 스킬 추가해줘")
"""

import io
import re
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from typing import Any

from app.backend.services.json_modify_tools import (
    edit_enemies,
    edit_items,
    edit_levels,
    edit_map_villager,
    edit_skills,
)

# ──────────────────────────────────────────────────────────────
# 키워드 맵
# ──────────────────────────────────────────────────────────────

# 사용자 입력에서 어떤 단어가 나왔을 때 어떤 edit_enemies 커맨드로 매핑하는지 정의
ENEMY_KEYWORD_MAP: dict[str, str] = {
    "crow": "crow",
    "까마귀": "crow",
    "크로우": "crow",
    "demon": "demon",
    "데몬": "demon",
    "악마": "demon",
    "slime": "slime",
    "슬라임": "slime",
    "Slime": "slime",
    "skeleton": "skeleton",
    "스켈레톤": "skeleton",
    "해골": "skeleton",
    "Skeleton": "skeleton",
}

# edit_items 에서 현재 지원하는 아이템 목록
SUPPORTED_ITEMS: list[str] = ["독약", "회복물약", "마나물약"]

# edit_skills 에서 현재 지원하는 스킬 목록
SUPPORTED_SKILLS: list[str] = ["최후의일격", "전체공격", "회복마법", "버프"]


# ──────────────────────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────────────────────


def _run_main(main_fn, argv: list[str]) -> dict[str, Any]:
    """
    edit_*.main(argv) 를 호출하고 stdout/stderr 를 캡처해 구조체로 반환한다.
    실제 파일 I/O 는 각 edit_* 모듈이 직접 수행하므로 여기서는 건드리지 않는다.
    """
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    exit_code: int = 0

    try:
        with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
            exit_code = main_fn(argv)
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        exit_code = 1
        stderr_buf.write(str(e))

    return {
        "success": exit_code == 0,
        "exit_code": exit_code,
        "stdout": stdout_buf.getvalue().strip(),
        "stderr": stderr_buf.getvalue().strip(),
        "timestamp": datetime.now().isoformat(),
    }


def _extract_map_id(user_input: str) -> str:
    """사용자 입력에서 첫 번째 숫자를 맵 ID로 추출한다. 없으면 기본값 '1'."""
    match = re.search(r"(\d+)", user_input)
    return match.group(1) if match else "1"


def _extract_level(user_input: str) -> str:
    """사용자 입력에서 레벨 숫자를 추출한다. 없으면 기본값 '25'."""
    # "레벨 50", "50레벨", "레벨을 30으로" 등의 패턴 매칭
    match = re.search(r"(\d+)", user_input)
    if match:
        level = int(match.group(1))
        # 1-99 사이의 합리적인 레벨 값만 허용
        if 1 <= level <= 99:
            return str(level)
    return "25"  # 기본값


# ──────────────────────────────────────────────────────────────
# 개별 라우터
# ──────────────────────────────────────────────────────────────


def run_enemies(user_input: str) -> dict[str, Any]:
    """
    user_input 에서 적 종류를 파싱해 edit_enemies.main() 을 실행한다.
    ENEMY_KEYWORD_MAP 키워드 매칭 → "crow" 또는 "demon" 결정
    """
    lower = user_input.lower()
    cmd: str | None = next(
        (val for key, val in ENEMY_KEYWORD_MAP.items() if key in lower),
        None,
    )
    if cmd is None:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": (
                f"적 종류를 파악할 수 없습니다. 지원 키워드: {', '.join(ENEMY_KEYWORD_MAP.keys())}"
            ),
            "command": "",
            "timestamp": datetime.now().isoformat(),
        }

    result = _run_main(edit_enemies.main, [cmd])
    result["command"] = cmd
    return result


def run_items(user_input: str) -> dict[str, Any]:
    """
    user_input 에서 아이템명을 파싱해 edit_items.main() 을 실행한다.
    SUPPORTED_ITEMS 목록과 매칭
    """
    item: str | None = next(
        (name for name in SUPPORTED_ITEMS if name in user_input),
        None,
    )
    if item is None:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"지원하는 아이템: {', '.join(SUPPORTED_ITEMS)}",
            "command": "",
            "timestamp": datetime.now().isoformat(),
        }

    result = _run_main(edit_items.main, [item])
    result["command"] = item
    return result


def run_map_villager(user_input: str) -> dict[str, Any]:
    """
    user_input 에서 맵 번호와 옵션 플래그를 파싱해 edit_map_villager.main() 을 실행한다.
    - 숫자 → 맵 ID (없으면 기본값 "1")
    - '덮어' / 'force' → --force
    - '테스트' / 'dry'  → --dry-run
    """
    map_id = _extract_map_id(user_input)
    argv: list[str] = [map_id]

    lower = user_input.lower()
    if "덮어" in lower or "force" in lower:
        argv.append("--force")
    if "테스트" in lower or "dry" in lower:
        argv.append("--dry-run")

    result = _run_main(edit_map_villager.main, argv)
    result["command"] = " ".join(argv)
    return result


def run_levels(user_input: str) -> dict[str, Any]:
    """
    user_input 에서 레벨 값을 파싱해 edit_levels.main() 을 실행한다.
    - 숫자 → 목표 레벨 (없으면 기본값 "25")
    예: "레벨 50으로", "레벨을 30으로 설정", "초기 레벨 40"
    """
    level = _extract_level(user_input)
    argv: list[str] = [level]

    result = _run_main(edit_levels.main, argv)
    result["command"] = level
    return result


def run_skills(user_input: str) -> dict[str, Any]:
    """
    user_input 에서 스킬명을 파싱해 edit_skills.main() 을 실행한다.
    SUPPORTED_SKILLS 목록과 매칭
    """
    skill: str | None = next(
        (name for name in SUPPORTED_SKILLS if name in user_input),
        None,
    )
    if skill is None:
        return {
            "success": False,
            "exit_code": 2,
            "stdout": "",
            "stderr": f"지원하는 스킬: {', '.join(SUPPORTED_SKILLS)}",
            "command": "",
            "timestamp": datetime.now().isoformat(),
        }

    result = _run_main(edit_skills.main, [skill])
    result["command"] = skill
    return result
