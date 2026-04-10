"""event_filler — 이벤트 뼈대의 대사를 LLM으로 채운다.

YAML 전체 재출력 대신, 번호별 대사 요청 → 파싱 → 원본에 삽입.
구조(스위치, 좌표)는 변경하지 않음.
"""

import logging
import re
from typing import cast

from pydantic import TypeAdapter

from agent.core.llm_client import invoke_llm
from agent.generation.compilers.dsl_models import DslEvent
from agent.generation.models import GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.prompts.event_filler_prompt import build_event_filler_prompt
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_TEMPERATURE = 0.7
_FILL = "_FILL_"
_dsl_event_adapter: TypeAdapter = TypeAdapter(DslEvent)

# 대사 역할 설명 (프롬프트에 포함)
_FIELD_ROLE = {
    "dialogue": "기본 대사 (처음 만났을 때)",
    "hint_dialogue": "힌트 (퀘스트 진행 중, 간접 힌트)",
    "alt_dialogue": "보상/완료 대사 (퀘스트 완료 후)",
    "blocked_dialogue": "차단 안내 (조건 미충족 시)",
}


async def event_filler(state: GenerationState) -> dict:
    """이벤트 대사 채우기 노드."""
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    skeletons: dict[int, list] = state.get("event_skeletons") or {}

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "event_fill",
            "progress": 72,
            "message": "이벤트 대사 작성 중...",
        },
    )

    event_dsl: dict[int, list] = {}
    for spec in map_specs:
        map_id = spec.map_id
        skeleton_list = skeletons.get(map_id, [])
        if not skeleton_list:
            event_dsl[map_id] = []
            continue

        filled = await _fill_single_map(spec, game_spec, skeleton_list)
        event_dsl[map_id] = filled

    logger.info("event_filler 완료: %d개 맵", len(event_dsl))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "event_fill",
            "summary": f"{len(event_dsl)}개 맵 대사 작성 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("event_fill")
    return {"event_dsl": event_dsl, "completed_phases": completed}


# ── 맵 단위 처리 ────────────────────────────────────────────────────────────


async def _fill_single_map(
    map_spec: MapSpec,
    game_spec: GameSpec,
    skeletons: list,
) -> list:
    """맵 1개의 뼈대에 대사를 채운다."""
    # _FILL_ 위치 추출
    fill_requests = _extract_fill_requests(skeletons)
    if not fill_requests:
        return skeletons

    request_text = _format_fill_requests(fill_requests)

    for attempt in range(2):
        try:
            prompt = build_event_filler_prompt(map_spec, game_spec, request_text)
            raw = cast(str, await invoke_llm(prompt, temperature=_TEMPERATURE))
            filled_map = _parse_fill_response(raw)
            if filled_map:
                return _apply_fills(skeletons, filled_map)
        except Exception as e:
            logger.warning("Map%d 대사 채우기 시도 %d 실패: %s", map_spec.map_id, attempt + 1, e)

    logger.warning("Map%d 대사 채우기 실패 → 기본 대사 사용", map_spec.map_id)
    return _apply_default_dialogue(skeletons)


# ── _FILL_ 추출 ─────────────────────────────────────────────────────────────


def _extract_fill_requests(skeletons: list) -> list[tuple[int, str, str]]:
    """(이벤트 인덱스, 필드명, 역할 설명) 목록 추출."""
    requests: list[tuple[int, str, str]] = []
    dialogue_fields = ["dialogue", "alt_dialogue", "hint_dialogue", "blocked_dialogue"]

    for i, skeleton in enumerate(skeletons):
        d = skeleton.model_dump()
        event_type = d.get("type", "npc")
        event_name = d.get("name", f"이벤트{i + 1}")

        for field in dialogue_fields:
            if field not in d:
                continue
            val = d[field]
            if val == _FILL or val == [_FILL] or (isinstance(val, list) and _FILL in val):
                role = _FIELD_ROLE.get(field, field)
                # 추가 맥락
                context = f"[{event_name}] ({event_type})"
                if field == "alt_dialogue" and d.get("condition_switch"):
                    context += f" — {d['condition_switch']} 조건 충족 후"
                if field == "hint_dialogue" and d.get("hint_switch"):
                    context += f" — {d['hint_switch']} 조건 충족 후, 퀘스트 진행 중"
                requests.append((i, field, f"{context} {role}"))

        # shop dialogue (str)
        if event_type == "shop" and d.get("dialogue") == _FILL:
            requests.append((i, "dialogue", f"[{event_name}] (상점) 상점 인사말"))

    return requests


def _format_fill_requests(requests: list[tuple[int, str, str]]) -> str:
    """프롬프트에 들어갈 대사 요청 텍스트."""
    lines = []
    for idx, field, desc in requests:
        lines.append(f"{idx + 1}.{field}: {desc}")
    return "\n".join(lines)


# ── LLM 응답 파싱 ───────────────────────────────────────────────────────────

_RESPONSE_PATTERN = re.compile(r"^(\d+)\.(\w+):\s*(.+)$", re.MULTILINE)


def _parse_fill_response(raw: str) -> dict[tuple[int, str], str]:
    """LLM 응답에서 번호.필드: 대사 형식을 파싱."""
    result: dict[tuple[int, str], str] = {}
    for match in _RESPONSE_PATTERN.finditer(raw):
        idx = int(match.group(1)) - 1  # 1-based → 0-based
        field = match.group(2)
        text = match.group(3).strip().strip('"').strip("'")
        if text and text != _FILL and "FILL" not in text:
            result[(idx, field)] = text
    return result


# ── 대사 적용 ────────────────────────────────────────────────────────────────


def _apply_fills(
    skeletons: list,
    filled_map: dict[tuple[int, str], str],
) -> list:
    """파싱된 대사를 원본 스켈레톤에 적용."""
    result = []
    for i, skeleton in enumerate(skeletons):
        d = skeleton.model_dump()
        for (idx, field), text in filled_map.items():
            if idx != i:
                continue
            if field in d:
                # list 필드 (dialogue, alt_dialogue, hint_dialogue)
                if isinstance(d[field], list):
                    d[field] = [text]
                else:
                    d[field] = text

        # 남은 _FILL_ 제거
        d = _remove_remaining_fills(d)
        result.append(_dsl_event_adapter.validate_python(d))
    return result


def _remove_remaining_fills(d: dict) -> dict:
    """dict에 남은 _FILL_ 을 기본 대사로 교체."""
    # shop dialogue는 str 타입이므로 먼저 처리
    if d.get("type") == "shop" and d.get("dialogue") == _FILL:
        d["dialogue"] = "어서오세요! 좋은 물건이 많습니다."
        return d  # shop은 다른 대사 필드 없음

    defaults = {
        "dialogue": ["안녕하세요, 여행자님. 이곳에 오신 걸 환영합니다."],
        "alt_dialogue": ["감사합니다! 덕분에 큰 도움이 되었습니다."],
        "hint_dialogue": ["이 근처를 잘 살펴보세요. 단서가 있을 겁니다."],
        "blocked_dialogue": "아직 이쪽으로는 갈 수 없습니다.",
    }
    for field, default_val in defaults.items():
        if field in d:
            val = d[field]
            if val == _FILL or val == [_FILL] or (isinstance(val, list) and _FILL in val):
                d[field] = default_val
    return d


# ── 폴백 ────────────────────────────────────────────────────────────────────


def _apply_default_dialogue(skeletons: list) -> list:
    """_FILL_을 기본 대사로 교체 (폴백)."""
    result = []
    for skeleton in skeletons:
        d = skeleton.model_dump()
        d = _remove_remaining_fills(d)
        result.append(_dsl_event_adapter.validate_python(d))
    return result
