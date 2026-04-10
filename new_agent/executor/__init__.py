"""Executor node — structured plan 을 순차 실행한다.

executor_yb 의 핵심 흐름을 유지하되 handler tree 로 분해.
LLM 0회. 순수 Python CRUD.
"""

from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.backend.core.game_paths import get_game_data_path
from new_agent.executor.dispatch import dispatch_step
from new_agent.executor.utils.locks import game_locks

logger = logging.getLogger(__name__)


async def executor(state: dict) -> dict:
    """Executor node entry point.

    state 에서 execution_plan 을 받아 순차 실행한 뒤 결과를 반환한다.
    """
    execution_plan: list[dict] = state.get("execution_plan", [])
    game_id: str = state.get("game_id", "")
    retry_count: int = state.get("retry_count", 0)
    t0 = time.perf_counter()

    logger.info("─── executor START ─────────────────────────────")

    if not game_id:
        return _guard_error("game_id 가 없습니다", t0)
    if retry_count >= 2:
        return _guard_error("최대 재시도(2) 초과", t0)
    if not execution_plan:
        return _guard_error("execution_plan 이 비어 있습니다", t0)

    data_path = get_game_data_path(game_id)

    # 백업 생성
    backup_paths = _create_backups(data_path, execution_plan)

    # step 순차 실행
    changes_log: list[dict] = []
    modified_file_paths: list[str] = []
    step_results: dict[int, dict] = {}

    for step in execution_plan:
        sid = step.get("step_id", -1)
        action = step.get("action_type", "")
        target_file = step.get("target_file", "")
        target_info = dict(step.get("target_info") or {})
        ts = datetime.now().isoformat()

        # error step (planner 가 만든 에러)
        if action == "error":
            entry = {
                "step_id": sid,
                "action": action,
                "target_file": target_file,
                "success": False,
                "error": target_info.get("error", "plan 단계 에러"),
                "timestamp": ts,
            }
            changes_log.append(entry)
            step_results[sid] = entry
            continue

        # dispatch
        async with game_locks[game_id]:
            result = dispatch_step(data_path, action, target_file, target_info)

        entry = {
            "step_id": sid,
            "action": action,
            "target_file": target_file,
            "success": result.get("success", False),
            "error": result.get("error"),
            "entity_id": result.get("entity_id"),
            "data": result.get("data"),
            "modified_files": result.get("modified_files", []),
            "timestamp": ts,
        }

        changes_log.append(entry)
        step_results[sid] = entry
        modified_file_paths.extend(result.get("modified_files", []))

    elapsed = time.perf_counter() - t0
    ok = sum(1 for e in changes_log if e.get("success"))
    fail = sum(1 for e in changes_log if not e.get("success"))
    logger.info(
        "─── executor END (%.2fs steps=%d ok=%d fail=%d) ─────",
        elapsed, len(changes_log), ok, fail,
    )

    return {
        "changes_log": changes_log,
        "modified_file_paths": sorted(set(modified_file_paths)),
        "backup_paths": backup_paths,
    }


async def execute_one(
    game_id: str,
    step: dict,
) -> dict:
    """단일 step 실행. validator 의 partial retry 에서 사용."""
    data_path = get_game_data_path(game_id)
    action = step.get("action_type", "")
    target_file = step.get("target_file", "")
    target_info = dict(step.get("target_info") or {})
    ts = datetime.now().isoformat()

    async with game_locks[game_id]:
        result = dispatch_step(data_path, action, target_file, target_info)

    return {
        "step_id": step.get("step_id", -1),
        "action": action,
        "target_file": target_file,
        "success": result.get("success", False),
        "error": result.get("error"),
        "entity_id": result.get("entity_id"),
        "data": result.get("data"),
        "modified_files": result.get("modified_files", []),
        "timestamp": ts,
    }


def _create_backups(data_path: Path, plan: list[dict]) -> dict[str, str]:
    """실행 전 대상 파일 백업."""
    targets = set()
    for step in plan:
        tf = step.get("target_file", "")
        if tf:
            targets.add(tf)
    backup_dir = data_path / "_backups"
    backup_dir.mkdir(exist_ok=True)
    paths: dict[str, str] = {}
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    for tf in targets:
        src = data_path / tf
        if src.exists():
            dst = backup_dir / f"{tf}.{ts}.bak"
            shutil.copy2(src, dst)
            paths[tf] = str(dst)
    return paths


def _guard_error(msg: str, t0: float) -> dict:
    logger.error("[executor] guard: %s", msg)
    return {
        "changes_log": [
            {
                "success": False,
                "error": msg,
                "timestamp": datetime.now().isoformat(),
            }
        ],
        "modified_file_paths": [],
        "backup_paths": {},
    }
