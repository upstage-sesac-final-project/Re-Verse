"""game_index_resolve — operation IR 의 ID/참조를 GameIndex 로 확정.

definition_v2 가 출력한 operation_tuples 를 받아:
  1. subject.id 가 없으면 GameIndex 로 검색하여 채움
  2. subject.name 만 있고 file 이 잘못된 경우 → 다른 파일에서 검색하여 교정
  3. value.ref 를 GameIndex 로 해소 (System.json 타입 또는 엔티티 ID)

LLM 호출 0회, 순수 결정론.
"""

from __future__ import annotations

import logging
from typing import Any

from agent.game_index import (
    EntityEntry,
    find_entity,
    find_in_file,
    resolve_entity_ref,
    resolve_system_type,
)
from agent.constants import CATEGORY_TO_FILE, KIND_TO_SYSTEM_KEY
from agent.graph.state import AgentState

logger = logging.getLogger(__name__)


async def game_index_resolve(state: AgentState) -> dict:
    """operation_tuples 의 subject.id, value.ref 를 확정한다."""
    import time
    _t0 = time.perf_counter()
    logger.info("─── GameIndexResolve START ─────────────────────────")

    ops: list[dict] = state.get("operation_tuples", []) or []
    game_id: str = state.get("game_id", "game_001")

    if not ops:
        logger.info("─── GameIndexResolve END (empty input) ────────────")
        return {}

    resolved: list[dict] = []
    for op in ops:
        op = _resolve_subject(op, game_id)
        op = _resolve_value(op, game_id)
        resolved.append(op)

    elapsed = time.perf_counter() - _t0
    logger.info("[GameIndexResolve] %d ops resolved", len(resolved))
    logger.info(
        "─── GameIndexResolve END (elapsed=%.2fs, ops=%d) ──────",
        elapsed, len(resolved),
    )
    return {"operation_tuples": resolved}


def _resolve_subject(op: dict, game_id: str) -> dict:
    """subject 의 id 를 GameIndex 로 확정. file 도 잘못된 경우 교정."""
    subject = op.get("subject")
    if not subject:
        return op

    name = subject.get("name")
    if not name:
        return op

    file = op.get("file")

    # 이미 id 가 있으면 그대로
    if subject.get("id") is not None:
        return op

    # 1. 지정된 파일에서 검색
    if file:
        entry = find_in_file(game_id, file, name)
        if entry:
            op = dict(op)
            op["subject"] = {**subject, "id": entry.id, "name": entry.name}
            return op

    # 2. 전체 파일에서 검색 (file 잘못된 경우)
    candidates = find_entity(game_id, name)
    if not candidates:
        return op

    # 정확히 1곳 → file 교정
    if len(candidates) == 1:
        entry = candidates[0]
        if entry.file != file:
            logger.info(
                "[GameIndexResolve] '%s': file %s → %s (재라우팅)",
                name, file, entry.file,
            )
        op = dict(op)
        op["file"] = entry.file
        op["subject"] = {**subject, "id": entry.id, "name": entry.name}
        return op

    # 여러 곳 발견 → 지정된 file 우선
    if file:
        for c in candidates:
            if c.file == file:
                op = dict(op)
                op["subject"] = {**subject, "id": c.id, "name": c.name}
                return op

    # 첫 번째 사용
    entry = candidates[0]
    op = dict(op)
    op["file"] = entry.file
    op["subject"] = {**subject, "id": entry.id, "name": entry.name}
    return op


def _resolve_value(op: dict, game_id: str) -> dict:
    """value.ref 를 숫자 ID 로 해소. value 에 resolved_id 추가.

    equips 관련 장비의 경우, 게임 데이터에서 etypeId 를 직접 읽어
    type_hint 를 정확한 슬롯 이름으로 교정한다.
    """
    value = op.get("value")
    if not value or not isinstance(value, dict):
        return op

    ref = value.get("ref")
    if not ref:
        return op

    kind = value.get("kind", "")
    resolved_id: int | None = None

    # System.json 타입 배열
    if kind in KIND_TO_SYSTEM_KEY:
        resolved_id = resolve_system_type(game_id, KIND_TO_SYSTEM_KEY[kind], ref)

    # 엔티티 파일
    elif kind in CATEGORY_TO_FILE:
        resolved_id = resolve_entity_ref(game_id, CATEGORY_TO_FILE[kind], ref)

    # kind 가 모호하면 전체 검색
    else:
        candidates = find_entity(game_id, ref)
        if candidates:
            resolved_id = candidates[0].id

    if resolved_id is not None:
        value = dict(value)
        value["resolved_id"] = resolved_id
        op = dict(op)
        op["value"] = value

    # equips 장비일 때: 게임 데이터에서 etypeId 를 읽어 type_hint 교정
    field = op.get("field", "")
    if field == "equips" and kind in ("armor", "weapon") and ref:
        op = _enrich_equip_type_hint(op, game_id, kind, ref)

    return op


def _enrich_equip_type_hint(op: dict, game_id: str, kind: str, ref: str) -> dict:
    """장비의 etypeId 를 게임 데이터에서 읽어 type_hint 를 정확한 슬롯 이름으로 설정."""
    import json
    from pathlib import Path

    target_file = "Armors.json" if kind == "armor" else "Weapons.json"
    entry = find_in_file(game_id, target_file, ref)
    if not entry:
        return op

    # entry.id 로 실제 JSON 에서 etypeId 읽기
    try:
        from agent.utils.game_data_io import read_game_json
        data = read_game_json(game_id, target_file)
        if not isinstance(data, list):
            return op
        entity = None
        for e in data:
            if isinstance(e, dict) and e.get("id") == entry.id:
                entity = e
                break
        if not entity:
            return op

        etype_id = entity.get("etypeId")
        if etype_id is None:
            return op

        # etypeId → equipTypes 배열에서 슬롯 이름 가져오기
        system = read_game_json(game_id, "System.json")
        if isinstance(system, dict):
            equip_types = system.get("equipTypes", [])
            if isinstance(equip_types, list) and 0 <= etype_id < len(equip_types):
                slot_name = equip_types[etype_id]
                if slot_name:
                    value = dict(op.get("value") or {})
                    value["type_hint"] = slot_name
                    op = dict(op)
                    op["value"] = value
                    logger.info(
                        "[GameIndexResolve] equip type_hint 교정: '%s' → etypeId=%d → '%s'",
                        ref, etype_id, slot_name,
                    )
    except Exception as e:
        logger.warning("[GameIndexResolve] equip type_hint 교정 실패: %s", e)

    return op
