"""Executor node — structured plan 을 순차 실행한다.

executor_yb 의 핵심 흐름을 유지하되 handler tree 로 분해.
LLM 0회. 순수 Python CRUD.

핵심 메커니즘:
  - step_results: 이전 step 의 entity_id 를 다음 step 의 target_info 에 주입
  - reconciliation: target_info 에 id 가 없으면 name 으로 파일에서 재검색
  - condition: step 에 조건이 있으면 평가 후 skip
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from agent.editor.nodes.executor_v2.dispatch import dispatch_step
from agent.editor.nodes.executor_v2.utils.locks import game_locks
from agent.utils.game_data_io import get_game_data_dir

logger = logging.getLogger(__name__)


async def executor(state: dict) -> dict:
    """Executor node entry point."""
    execution_plan: list[dict] = state.get("execution_plan", [])
    game_id: str = state.get("game_id", "")
    retry_count: int = state.get("retry_count", 0)
    t0 = time.perf_counter()

    logger.info("─── executor START ─────────────────────────────")

    # retry 추적 상태 초기화 (매 실행 시작 시)
    from agent.editor.nodes.validator.retry_loop import reset_retry_state

    reset_retry_state()

    if not game_id:
        return _guard_error("game_id 가 없습니다", t0)
    if retry_count >= 2:
        return _guard_error("최대 재시도(2) 초과", t0)
    if not execution_plan:
        return _guard_error("execution_plan 이 비어 있습니다", t0)

    data_path = Path(get_game_data_dir(game_id))
    backup_paths = _create_backups(data_path, execution_plan)

    changes_log: list[dict] = []
    modified_file_paths: list[str] = []
    step_results: dict[int, dict] = {}  # sid → {entity_id, data, ...}

    for step in execution_plan:
        sid = step.get("step_id", -1)
        action = step.get("action_type", "")
        target_file = step.get("target_file", "")
        target_info = dict(step.get("target_info") or {})
        depends_on = step.get("depends_on", [])
        ts = datetime.now().isoformat()

        # ── error step ──
        if action == "error":
            entry = _make_entry(
                sid, action, target_file, False, error=target_info.get("error", "plan 에러"), ts=ts
            )
            changes_log.append(entry)
            step_results[sid] = entry
            continue

        # ── condition 평가 ──
        if _should_skip(step, step_results):
            entry = _make_entry(sid, action, target_file, True, ts=ts, skipped=True)
            changes_log.append(entry)
            step_results[sid] = entry
            logger.info("[executor] step %d SKIPPED (condition)", sid)
            continue

        # ── step_results 에서 이전 step 결과 주입 ──
        target_info = _inject_prev_results(target_info, depends_on, step_results, data_path)

        # ── name → id reconciliation ──
        target_info = _reconcile_id(target_info, target_file, data_path, action)

        logger.info(
            "[executor] step %d: %s.%s target=%s",
            sid,
            target_file,
            action,
            json.dumps(target_info, ensure_ascii=False)[:200],
        )

        # ── dispatch ──
        async with game_locks[game_id]:
            result = dispatch_step(data_path, action, target_file, target_info)

        entry = _make_entry(
            sid,
            action,
            target_file,
            success=result.get("success", False),
            error=result.get("error"),
            entity_id=result.get("entity_id"),
            data=result.get("data"),
            modified_files=result.get("modified_files", []),
            ts=ts,
        )
        changes_log.append(entry)
        step_results[sid] = entry
        modified_file_paths.extend(result.get("modified_files", []))

    elapsed = time.perf_counter() - t0
    ok = sum(1 for e in changes_log if e.get("success"))
    fail = sum(1 for e in changes_log if not e.get("success") and not e.get("skipped"))
    logger.info(
        "─── executor END (%.2fs steps=%d ok=%d fail=%d) ─────",
        elapsed,
        len(changes_log),
        ok,
        fail,
    )

    return {
        "changes_log": changes_log,
        "modified_file_paths": sorted(set(modified_file_paths)),
        "backup_paths": backup_paths,
    }


async def execute_one(game_id: str, step: dict) -> dict:
    """단일 step 실행. validator 의 partial retry 에서 사용."""
    data_path = Path(get_game_data_dir(game_id))
    action = step.get("action_type", "")
    target_file = step.get("target_file", "")
    target_info = dict(step.get("target_info") or {})

    # MapInfos.json 액션 정규화 (executor._normalize_structured_action 와 동일)
    if target_file == "MapInfos.json":
        if action == "create":
            action = "create_map"
        elif action == "delete":
            action = "delete_map"

    target_info = _reconcile_id(target_info, target_file, data_path, action)
    ts = datetime.now().isoformat()

    async with game_locks[game_id]:
        result = dispatch_step(data_path, action, target_file, target_info)

    return _make_entry(
        step.get("step_id", -1),
        action,
        target_file,
        success=result.get("success", False),
        error=result.get("error"),
        entity_id=result.get("entity_id"),
        data=result.get("data"),
        modified_files=result.get("modified_files", []),
        ts=ts,
    )


# ──────────────────────────────────────────────
# step_results 전파
# ──────────────────────────────────────────────


def _inject_prev_results(
    target_info: dict,
    depends_on: list[int],
    step_results: dict[int, dict],
    data_path: Path,
) -> dict:
    """이전 step 의 결과를 target_info 에 주입한다.

    주요 패턴:
      - 이전 create step 의 entity_id → updates 내 참조 해소
      - _equip.item_id, _add_learning.skill_id 등이 None 이면 이전 결과에서 채움
      - (신규) Actor create 의 target_info.classId=None → 이전 Classes create 에서 주입
    """
    info = dict(target_info)

    # 의존 step 들의 결과 수집. depends_on 이 비어있으면 이전 전체 성공 create 를
    # 훑는다 (Planner auto-prepend 가 Actor step 의 depends_on 을 채우지 않는
    # 경로 대응).
    prev_ids: dict[str, int] = {}  # target_file → entity_id
    sids = depends_on or list(step_results.keys())
    for dep_sid in sids:
        prev = step_results.get(dep_sid, {})
        if prev.get("success") and prev.get("entity_id") is not None:
            prev_file = prev.get("target_file", "")
            # 같은 파일에 여러 create 가 있으면 마지막 (가장 최근) 것 우선
            prev_ids[prev_file] = prev["entity_id"]

    # Actor create 등 create op 의 top-level classId = None → 이전 Classes 주입
    if "classId" in info and info.get("classId") is None:
        new_class_id = prev_ids.get("Classes.json")
        if new_class_id is not None:
            info["classId"] = new_class_id
            logger.info(
                "[reconcile] Actor create.classId=None → prev Classes.json id=%d 주입",
                new_class_id,
            )

    updates = info.get("updates")
    if not isinstance(updates, dict):
        return info

    new_updates = dict(updates)

    # _equip: armor_id / weapon_id 가 None 이면 이전 Armors/Weapons create 에서 채움
    equip = new_updates.get("_equip")
    if isinstance(equip, dict) and equip.get("item_id") is None:
        equip["item_id"] = prev_ids.get("Armors.json") or prev_ids.get("Weapons.json")

    # _add_learning: skill_id 가 None 이면 이전 Skills create 에서 채움
    learn = new_updates.get("_add_learning")
    if isinstance(learn, dict) and learn.get("skill_id") is None:
        learn["skill_id"] = prev_ids.get("Skills.json")

    # _add_action: skill_id
    act = new_updates.get("_add_action")
    if isinstance(act, dict) and act.get("skill_id") is None:
        act["skill_id"] = prev_ids.get("Skills.json")

    # _add_drop_item: item_id
    drop = new_updates.get("_add_drop_item")
    if isinstance(drop, dict) and drop.get("item_id") is None:
        drop["item_id"] = prev_ids.get("Items.json")

    # _equip.etype_id 가 None 이면 이전 System append 에서 채움
    if isinstance(equip, dict) and equip.get("etype_id") is None:
        equip["etype_id"] = prev_ids.get("System.json")

    # classId 가 None 이면 이전 Classes create 에서 채움
    if "classId" in new_updates and new_updates["classId"] is None:
        new_updates["classId"] = prev_ids.get("Classes.json")

    info["updates"] = new_updates
    return info


# ──────────────────────────────────────────────
# name → id reconciliation
# ──────────────────────────────────────────────

_ENTITY_FILES = frozenset(
    {
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "States.json",
    }
)


def _reconcile_id(
    target_info: dict,
    target_file: str,
    data_path: Path,
    action: str,
) -> dict:
    """target_info 에 id 가 없고 name 이 있으면 파일에서 검색해 id 를 채운다."""
    if target_file not in _ENTITY_FILES:
        return target_info
    if action in ("create", "search", "list", "append_system_type"):
        return target_info  # create 는 id 불필요

    info = dict(target_info)
    entity_id = _extract_id(info)
    name = info.get("name", "").strip()

    if entity_id is not None:
        # id 가 있으면 유효성만 확인
        data = _load_json_safe(data_path, target_file)
        if isinstance(data, list) and 0 <= entity_id < len(data):
            entry = data[entity_id]
            if isinstance(entry, dict):
                # name 교차 검증
                actual_name = entry.get("name", "")
                if name and actual_name and name.lower() != actual_name.lower():
                    # id 는 있지만 name 이 다름 → name 기반 재검색
                    logger.warning(
                        "[reconcile] id=%d name 불일치: '%s' vs '%s', name 으로 재검색",
                        entity_id,
                        name,
                        actual_name,
                    )
                    found = _find_by_name(data, name)
                    if found is not None:
                        info["id"] = found
                        return info
        return info

    if not name:
        return info

    # id 없음 → name 으로 검색
    data = _load_json_safe(data_path, target_file)
    if not isinstance(data, list):
        return info
    found = _find_by_name(data, name)
    if found is not None:
        info["id"] = found
        logger.info("[reconcile] '%s' in %s → id=%d", name, target_file, found)
    else:
        logger.warning("[reconcile] '%s' not found in %s", name, target_file)

    return info


def _extract_id(info: dict) -> int | None:
    """target_info 에서 entity id 추출."""
    for key in (
        "id",
        "entity_id",
        "actor_id",
        "skill_id",
        "item_id",
        "class_id",
        "enemy_id",
        "state_id",
        "weapon_id",
        "armor_id",
    ):
        val = info.get(key)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _find_by_name(data: list, name: str, threshold: float = 0.6) -> int | None:
    """배열에서 name 으로 entity id 검색. 완전일치 → fuzzy."""
    t = name.strip().lower()
    # 완전 일치
    for entry in data:
        if isinstance(entry, dict) and str(entry.get("name") or "").strip().lower() == t:
            return entry.get("id")
    # fuzzy
    best_id, best_ratio = None, 0.0
    for entry in data:
        if not isinstance(entry, dict):
            continue
        entry_name = str(entry.get("name") or "").strip().lower()
        if not entry_name:
            continue
        ratio = SequenceMatcher(None, t, entry_name).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_id = entry.get("id")
    if best_ratio >= threshold:
        return best_id
    return None


def _load_json_safe(data_path: Path, filename: str) -> Any:
    fp = data_path / filename
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


# ──────────────────────────────────────────────
# condition 평가
# ──────────────────────────────────────────────


def _should_skip(step: dict, step_results: dict[int, dict]) -> bool:
    """step 의 condition 을 평가해서 skip 여부를 결정한다.

    condition 형태:
      - 구조화: {"skip_if_exists": True} 또는 {"skip_if_not_exists": True}
      - 한국어 문자열 (하위 호환): "존재하지 않으면", "없으면" 등
      - depends_on 의 결과에 따라 판단
    """
    condition = step.get("condition")
    if not condition:
        return False

    depends_on = step.get("depends_on", [])

    if isinstance(condition, dict):
        if condition.get("skip_if_exists"):
            # 의존 step 이 성공(= 대상이 이미 존재)이면 skip
            return any(step_results.get(d, {}).get("success") for d in depends_on)
        if condition.get("skip_if_not_exists"):
            return any(not step_results.get(d, {}).get("success") for d in depends_on)

    if isinstance(condition, str):
        # 한국어 문자열 하위 호환
        skip_phrases = ("존재하지 않", "없을 경우", "없으면", "없을 때")
        if any(p in condition for p in skip_phrases):
            return any(not step_results.get(d, {}).get("success") for d in depends_on)

    return False


# ──────────────────────────────────────────────
# util
# ──────────────────────────────────────────────


def _make_entry(
    sid: int,
    action: str,
    target_file: str,
    success: bool,
    error: str | None = None,
    entity_id: int | None = None,
    data: Any = None,
    modified_files: list[str] | None = None,
    ts: str = "",
    skipped: bool = False,
) -> dict:
    entry: dict[str, Any] = {
        "step_id": sid,
        "action": action,
        "tool_name": f"structured_{target_file.replace('.json', '').lower()}_{action}",
        "target_file": target_file,
        "success": success,
        "timestamp": ts or datetime.now().isoformat(),
    }
    if error:
        entry["error"] = error
    if entity_id is not None:
        entry["entity_id"] = entity_id
    if data is not None:
        entry["data"] = data
    if modified_files:
        entry["modified_files"] = modified_files
    if skipped:
        entry["skipped"] = True
    return entry


def _create_backups(data_path: Path, plan: list[dict]) -> dict[str, str]:
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
                "step_id": -1,
                "action": "guard",
                "tool_name": "guard_error",
                "target_file": "",
                "success": False,
                "error": msg,
                "timestamp": datetime.now().isoformat(),
            }
        ],
        "modified_file_paths": [],
        "backup_paths": {},
    }
