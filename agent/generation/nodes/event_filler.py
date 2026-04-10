"""event_filler — 이벤트 뼈대의 대사를 LLM으로 채운다.

event_scaffolder가 생성한 _FILL_ 플레이스홀더를 자연스러운 대사로 교체.
구조(스위치, 좌표)는 변경하지 않음.
"""

import logging
from typing import cast

import yaml
from pydantic import TypeAdapter, ValidationError

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


async def _fill_single_map(
    map_spec: MapSpec,
    game_spec: GameSpec,
    skeletons: list,
) -> list:
    """맵 1개의 뼈대에 대사를 채운다."""
    skeleton_dicts = [e.model_dump() for e in skeletons]
    skeleton_yaml = yaml.dump(
        {"events": skeleton_dicts}, allow_unicode=True, default_flow_style=False
    )

    if _FILL not in skeleton_yaml:
        return skeletons

    for attempt in range(2):
        try:
            prompt = build_event_filler_prompt(map_spec, game_spec, skeleton_yaml)
            raw = cast(str, await invoke_llm(prompt, temperature=_TEMPERATURE))
            filled = _parse_filled_yaml(raw, skeletons)
            if filled is not None:
                return filled
        except Exception as e:
            logger.warning("Map%d 대사 채우기 시도 %d 실패: %s", map_spec.map_id, attempt + 1, e)

    logger.warning("Map%d 대사 채우기 실패 → 기본 대사 사용", map_spec.map_id)
    return _apply_default_dialogue(skeletons)


def _parse_filled_yaml(raw: str, originals: list) -> list | None:
    """LLM 응답 파싱. 구조는 원본 유지, 대사만 교체."""
    try:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

        data = yaml.safe_load(text)
        if not isinstance(data, dict) or "events" not in data:
            return None

        events = data["events"] or []
        if len(events) != len(originals):
            logger.warning("LLM 출력 이벤트 수 불일치: %d vs %d", len(events), len(originals))

        result = []
        for i, orig in enumerate(originals):
            if i < len(events):
                merged = _merge_dialogue_only(orig.model_dump(), events[i])
                result.append(_dsl_event_adapter.validate_python(merged))
            else:
                result.append(orig)

        return result
    except (yaml.YAMLError, ValidationError) as e:
        logger.warning("filled YAML 파싱 실패: %s", e)
        return None


def _merge_dialogue_only(original: dict, filled: dict) -> dict:
    """filled에서 대사 필드만 가져오고 나머지는 original 유지."""
    dialogue_fields = {
        "dialogue",
        "alt_dialogue",
        "hint_dialogue",
        "lines",
    }
    merged = dict(original)
    for field in dialogue_fields:
        if (
            field in filled
            and filled[field]
            and filled[field] != [_FILL]
            and filled[field] != _FILL
        ):
            merged[field] = filled[field]
    # blocked_dialogue (str)
    if (
        "blocked_dialogue" in filled
        and isinstance(filled.get("blocked_dialogue"), str)
        and filled["blocked_dialogue"] != _FILL
    ):
        merged["blocked_dialogue"] = filled["blocked_dialogue"]
    # shop dialogue (str)
    if (
        original.get("type") == "shop"
        and "dialogue" in filled
        and isinstance(filled.get("dialogue"), str)
        and filled["dialogue"] != _FILL
    ):
        merged["dialogue"] = filled["dialogue"]
    return merged


def _apply_default_dialogue(skeletons: list) -> list:
    """_FILL_을 기본 대사로 교체 (폴백)."""
    defaults = {
        "npc": {
            "dialogue": ["..."],
            "alt_dialogue": ["감사합니다."],
            "hint_dialogue": ["잘 찾아보세요."],
        },
        "shop": {"dialogue": "어서오세요."},
        "transfer": {"blocked_dialogue": "아직 갈 수 없습니다."},
    }
    result = []
    for skeleton in skeletons:
        d = skeleton.model_dump()
        event_type = d.get("type", "npc")
        type_defaults = defaults.get(event_type, {})
        for field, default_val in type_defaults.items():
            if field in d and (d[field] == [_FILL] or d[field] == _FILL):
                d[field] = default_val
        result.append(_dsl_event_adapter.validate_python(d))
    return result
