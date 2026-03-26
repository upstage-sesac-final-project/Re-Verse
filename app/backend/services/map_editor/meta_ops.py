"""맵 메타정보 수정 연산."""

from typing import Any

# 수정 허용 필드 화이트리스트
ALLOWED_META_FIELDS: frozenset[str] = frozenset(
    {
        "displayName",  # 맵 표시 이름
        "encounterStep",  # 인카운터 빈도 (걸음 수)
        "tilesetId",  # 타일셋 ID
        "parallaxName",  # 원경 이미지명
        "parallaxLoopX",  # 원경 가로 반복
        "parallaxLoopY",  # 원경 세로 반복
        "parallaxSx",  # 원경 X 스크롤 속도
        "parallaxSy",  # 원경 Y 스크롤 속도
        "scrollType",  # 스크롤 타입 (0=고정 1=가로루프 2=세로루프 3=양방향)
        "disableDashing",  # 달리기 금지
        "specifyBattleback",  # 전투 배경 개별 지정 여부
        "battleback1Name",  # 전투 배경 아래
        "battleback2Name",  # 전투 배경 위
        "autoplayBgm",  # BGM 자동 재생
        "autoplayBgs",  # BGS 자동 재생
    }
)

# BGM/BGS는 중첩 dict — 별도 처리
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
                f"'{field}'은 수정할 수 없는 필드입니다. "
                f"허용 필드: {sorted(ALLOWED_META_FIELDS | _AUDIO_FIELDS)}"
            )

    return map_data


def _update_audio(map_data: dict[str, Any], field: str, value: Any) -> None:
    """bgm/bgs 중첩 객체를 부분 업데이트한다."""
    if not isinstance(value, dict):
        raise ValueError(f"'{field}' 값은 dict여야 합니다. 예: {{'name': 'Town', 'volume': 90}}")

    unknown = set(value) - _AUDIO_SUBFIELDS
    if unknown:
        raise ValueError(f"'{field}' 허용 서브필드: {sorted(_AUDIO_SUBFIELDS)}, 불허: {unknown}")

    map_data[field].update(value)
