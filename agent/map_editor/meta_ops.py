"""맵 메타정보 수정 연산."""

from typing import Any

ALLOWED_META_FIELDS: frozenset[str] = frozenset(
    {
        "displayName",
        "encounterStep",
        "tilesetId",
        "parallaxName",
        "parallaxLoopX",
        "parallaxLoopY",
        "parallaxSx",
        "parallaxSy",
        "scrollType",
        "disableDashing",
        "specifyBattleback",
        "battleback1Name",
        "battleback2Name",
        "autoplayBgm",
        "autoplayBgs",
    }
)

_AUDIO_FIELDS: frozenset[str] = frozenset({"bgm", "bgs"})
_AUDIO_SUBFIELDS: frozenset[str] = frozenset({"name", "pan", "pitch", "volume"})


def update_meta(map_data: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """맵 메타정보를 수정한다.

    params 예시:
        {"displayName": "마을 광장"}
        {"encounterStep": 50}
        {"bgm": {"name": "Town", "volume": 90, "pitch": 100, "pan": 0}}
        {"autoplayBgm": True, "bgm": {"name": "Town", "volume": 90, "pitch": 100, "pan": 0}}
    """
    for field, value in params.items():
        if field in _AUDIO_FIELDS:
            _update_audio(map_data, field, value)
        elif field in ALLOWED_META_FIELDS:
            map_data[field] = value
        else:
            raise ValueError(
                f"'{field}'은 수정 불가 필드입니다. "
                f"허용 필드: {sorted(ALLOWED_META_FIELDS | _AUDIO_FIELDS)}"
            )

    return map_data


def _update_audio(map_data: dict[str, Any], field: str, value: Any) -> None:
    if not isinstance(value, dict):
        raise ValueError(f"'{field}' 값은 dict여야 합니다. 예: {{'name': 'Town', 'volume': 90}}")

    unknown = set(value) - _AUDIO_SUBFIELDS
    if unknown:
        raise ValueError(f"'{field}' 허용 서브필드: {sorted(_AUDIO_SUBFIELDS)}, 불허: {unknown}")

    if field not in map_data or not isinstance(map_data[field], dict):
        map_data[field] = {}
    map_data[field].update(value)
