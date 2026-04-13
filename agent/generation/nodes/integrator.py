"""H 노드 — integrator: 모든 중간 결과물 → 완전한 RPG Maker MZ 프로젝트.

Phase 2: 에셋 파일만 조립 (Map*.json, System.json 완전체는 Phase 3+).
canonical: docs/The_world/integrator_assembly.md
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.H
"""

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from agent.generation.mapgen import calculate_spawn_point
from agent.generation.mapgen.tile_checker import find_nearest_safe_coord
from agent.generation.models import GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable, normalize_switch_name
from agent.generation.state import GenerationState
from app.backend.core.config import settings

logger = logging.getLogger(__name__)

# ── base_game 고정 파일 로드 ────────────────────────────────────────────────

_BASE_GAME_DATA = Path(settings.BASE_GAME_PATH) / "data"


def _load_base_game_file(fname: str) -> list | dict:
    """base_game/data/{fname}을 읽어 반환. 실패 시 [None] fallback."""
    path = _BASE_GAME_DATA / fname
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("base_game %s 로드 실패, [None] fallback: %s", fname, e)
        return [None]


@lru_cache(maxsize=1)
def get_available_characters() -> dict[str, str]:
    """base_game/img/characters 폴더의 실제 파일 목록을 {순수이름: 실제파일명}으로 반환."""
    char_path = Path(settings.BASE_GAME_PATH) / "img" / "characters"
    mapping = {}
    if char_path.exists():
        for f in char_path.glob("*.png"):
            full_name = f.stem  # !$Gate1
            # 기호를 제거한 순수 이름 추출 (대소문자 무시)
            clean_name = full_name.replace("!", "").replace("$", "").lower()
            mapping[clean_name] = full_name
    return mapping


def fix_character_filenames(map_json: dict) -> dict:
    """실제 파일 목록과 대조하여 캐릭터 이름을 보정함."""
    available_chars = get_available_characters()
    if not available_chars:
        return map_json

    events = map_json.get("events", [])
    for event in events:
        if event is None:
            continue
        pages = event.get("pages", [])
        for page in pages:
            image = page.get("image", {})
            if image and image.get("characterName"):
                cname = image["characterName"]
                # 1. 기호를 제거한 순수 이름으로 실제 파일 찾기
                clean_lookup = cname.replace("!", "").replace("$", "").lower()

                if clean_lookup in available_chars:
                    real_name = available_chars[clean_lookup]
                    if cname != real_name:
                        logger.info("캐릭터 에셋 보정: %s -> %s", cname, real_name)
                        image["characterName"] = real_name
    return map_json


def load_base_tilesets() -> list[dict]:
    """base_game에서 표준 Tilesets.json을 로드하고 1~6번 슬롯만 반환."""
    base_path = _BASE_GAME_DATA / "Tilesets.json"

    # 1. 파일 로드 시도
    if base_path.exists():
        try:
            with open(base_path, encoding="utf-8") as f:
                tilesets = json.load(f)
                # 0번(null)과 1~6번까지만 슬라이싱 (MZ 표준)
                filtered = [
                    ts
                    for ts in tilesets
                    if ts is None or (isinstance(ts, dict) and ts.get("id", 0) <= 6)
                ]
                logger.info(
                    "Tilesets.json 로드 성공: %d개의 타일셋 데이터를 읽어왔습니다.", len(filtered)
                )
                return filtered
        except Exception as e:
            logger.error("Tilesets.json 파일은 존재하지만 읽기 실패: %s", e)
    else:
        logger.error("Tilesets.json 파일을 찾을 수 없습니다: %s", base_path)

    # 2. 로드 실패 시 표준 폴백 (MZ 기본 구성)
    logger.warning(
        "CRITICAL: Tilesets.json 로드 실패! 모든 타일의 flags가 0(통행 가능)으로 초기화된 위험한 폴백 데이터를 사용합니다."
    )
    return [
        None,
        {
            "id": 1,
            "name": "필드",
            "mode": 0,
            "tilesetNames": ["World_A1", "World_A2", "World_B", "World_C", "", "", "", "", ""],
            "flags": [0] * 8192,
            "note": "FALLBACK-DATA",
        },
        {
            "id": 2,
            "name": "외곽",
            "mode": 1,
            "tilesetNames": [
                "Outside_A1",
                "Outside_A2",
                "Outside_A3",
                "Outside_A4",
                "Outside_A5",
                "Outside_B",
                "Outside_C",
                "",
                "",
            ],
            "flags": [0] * 8192,
            "note": "FALLBACK-DATA",
        },
        {
            "id": 3,
            "name": "내부",
            "mode": 1,
            "tilesetNames": [
                "Inside_A1",
                "Inside_A2",
                "Inside_A4",
                "Inside_A5",
                "Inside_B",
                "Inside_C",
                "",
                "",
                "",
            ],
            "flags": [0] * 8192,
            "note": "FALLBACK-DATA",
        },
        {
            "id": 4,
            "name": "던전",
            "mode": 1,
            "tilesetNames": [
                "Dungeon_A1",
                "Dungeon_A2",
                "Dungeon_A4",
                "Dungeon_A5",
                "Dungeon_B",
                "Dungeon_C",
                "",
                "",
                "",
            ],
            "flags": [0] * 8192,
            "note": "FALLBACK-DATA",
        },
        {
            "id": 5,
            "name": "SF 외곽",
            "mode": 1,
            "tilesetNames": [
                "SF_Outside_A1",
                "SF_Outside_A2",
                "SF_Outside_A3",
                "SF_Outside_A4",
                "SF_Outside_A5",
                "SF_Outside_B",
                "SF_Outside_C",
                "",
                "",
            ],
            "flags": [0] * 8192,
            "note": "FALLBACK-DATA",
        },
        {
            "id": 6,
            "name": "SF 내부",
            "mode": 1,
            "tilesetNames": [
                "SF_Inside_A1",
                "SF_Inside_A2",
                "SF_Inside_A4",
                "SF_Inside_A5",
                "SF_Inside_B",
                "SF_Inside_C",
                "",
                "",
                "",
            ],
            "flags": [0] * 8192,
            "note": "FALLBACK-DATA",
        },
    ]


def _audio(name: str = "", volume: int = 90, pitch: int = 100) -> dict:
    return {"name": name, "volume": volume, "pitch": pitch, "pan": 0}


def _default_vehicle() -> dict:
    return {
        "bgm": _audio(),
        "characterIndex": 0,
        "characterName": "",
        "startMapId": 0,
        "startX": 0,
        "startY": 0,
    }


def _default_terms() -> dict:
    return {
        "basic": [
            "레벨",  # 0 level
            "Lv",  # 1 levelA (약어)
            "HP",  # 2 hp
            "HP",  # 3 hpA (약어)
            "MP",  # 4 mp
            "MP",  # 5 mpA (약어)
            "TP",  # 6 tp
            "TP",  # 7 tpA (약어)
            "EXP",  # 8 exp
            "EXP",  # 9 expA (약어)
        ],
        "commands": [
            "싸운다",  # 0  fight
            "도망",  # 1  escape
            "공격",  # 2  attack
            "방어",  # 3  guard
            "아이템",  # 4  item
            "스킬",  # 5  skill
            "장비",  # 6  equip
            "스탯",  # 7  status
            "정렬",  # 8  formation
            "저장",  # 9  save
            "게임 종료",  # 10 gameEnd
            "옵션",  # 11 options  ← TextManager.options
            "무기",  # 12 weapon
            "방어구",  # 13 armor
            "핵심 아이템",  # 14 keyItem
            "장비",  # 15 equip2
            "최적화",  # 16 optimize
            "모두 해제",  # 17 clear
            "새 게임",  # 18 newGame  ← TextManager.newGame
            "이어하기",  # 19 continue ← TextManager.continue_
            None,  # 20
            "타이틀로",  # 21
            "취소",  # 22
            None,  # 23
            "구매",  # 24
            "판매",  # 25
        ],
        "params": [
            "최대 HP",
            "최대 MP",
            "공격력",
            "방어력",
            "마법력",
            "마법방어",
            "민첩성",
            "행운",
        ],
        "messages": {
            "alwaysDash": "항상 대쉬",
            "commandRemember": "명령 기억",
            "touchUI": "터치 UI",
            "bgmVolume": "BGM 볼륨",
            "bgsVolume": "BGS 볼륨",
            "meVolume": "ME 볼륨",
            "seVolume": "SE 볼륨",
            "possession": "갖고 있는 수",
            "expTotal": "현재 %1",
            "expNext": "다음 %1까지",
            "saveMessage": "어느 파일에 저장할까요?",
            "loadMessage": "어떤 파일을 로드할까요?",
            "file": "파일",
            "autosave": "자동 저장",
            "partyName": "%1 파티",
            "emerge": "%1 이(가) 나타났습니다!",
            "preemptive": "%1 이(가) 우위를 점했습니다!",
            "surprise": "%1 이(가) 습격당했습니다!",
            "escapeStart": "%1이(가) 도망가기 시작했습니다!",
            "escapeFailure": "그러나, 탈출할 수 없었습니다!",
            "victory": "%1 이(가) 승리했습니다!",
            "defeat": "%1 이(가) 패배했습니다.",
            "obtainExp": "%1 의 %2 을(를) 획득하였습니다!",
            "obtainGold": "%1\\G를 손에 넣었습니다!",
            "obtainItem": "%1을(를) 손에 넣었습니다!",
            "levelUp": "%1은(는) 이제 %2 %3입니다!",
            "obtainSkill": "%1을(를) 습득하였습니다!",
            "useItem": "%1이(가) %2을(를) 이용합니다!",
            "criticalToEnemy": "회심의 일격!!",
            "criticalToActor": "피눈물나는 강타!!",
            "actorDamage": "%1은(는) %2의 피해를 입었습니다!",
            "actorRecovery": "%1의 %2이(가) %3 회복됐습니다!",
            "actorGain": "%1의 %2이(가) %3 증가했습니다!",
            "actorLoss": "%1의 %2이(가) %3 감소했습니다!",
            "actorDrain": "%1은(는) %2을(를) %3 빼앗겼습니다!",
            "actorNoDamage": "%1은(는) 피해를 입지 않았습니다!",
            "actorNoHit": "빗나갔습니다! %1은(는) 피해를 입지 않았습니다!",
            "enemyDamage": "%1에게 %2의 피해를 입혔습니다!",
            "enemyRecovery": "%1의 %2이(가) %3 회복됐습니다!",
            "enemyGain": "%1의 %2이(가) %3 증가했습니다!",
            "enemyLoss": "%1의 %2이(가) %3 감소했습니다!",
            "enemyDrain": "%1의 %2을(를) %3 빼앗았습니다!",
            "enemyNoDamage": "%1에게 피해를 입힐 수 없습니다!",
            "enemyNoHit": "빗나갔습니다! %1에게 피해를 입힐 수 없습니다!",
            "evasion": "%1이(가) 공격을 회피했습니다!",
            "magicEvasion": "%1이(가) 마법을 무효화했습니다!",
            "magicReflection": "%1이(가) 마법을 반사했습니다!",
            "counterAttack": "%1이(가) 반격했습니다!",
            "substitute": "%1이(가) %2을(를) 보호했습니다!",
            "buffAdd": "%1의 %2이(가) 상승했습니다!",
            "debuffAdd": "%1의 %2이(가) 감소했습니다!",
            "buffRemove": "%1의 %2이(가) 정상으로 돌아왔습니다!",
            "actionFailure": "%1에는 아무 영향이 없었습니다!",
        },
    }


def _default_sounds() -> list:
    return [_audio("Cursor1")] * 24  # RPG Maker MZ 기본 24개 SE 슬롯


def _default_attack_motions() -> list[dict]:
    return [{"type": i, "weaponImageId": 0} for i in range(10)]


# ── 타이틀 화면 자동 선택 (테마 키워드 → 배경/프레임/BGM) ───────────────────

_TITLE_BG_KEYWORDS: dict[str, str] = {
    "판타지": "Sword",
    "fantasy": "Sword",
    "기사": "Sword",
    "중세": "Gate",
    "medieval": "Gate",
    "왕국": "Gate",
    "해적": "Beach",
    "pirate": "Beach",
    "바다": "Beach",
    "ocean": "Beach",
    "숲": "Bigtree",
    "forest": "Bigtree",
    "자연": "Bigtree",
    "정글": "Jungle",
    "jungle": "Jungle",
    "사막": "Oasis",
    "desert": "Oasis",
    "눈": "Snow",
    "snow": "Snow",
    "겨울": "Snow",
    "얼음": "Snow",
    "산": "Mountain",
    "mountain": "Mountain",
    "우주": "Universe",
    "space": "Universe",
    "sf": "Universe",
    "사이버": "Universe",
    "폐허": "Ruins",
    "ruin": "Ruins",
    "종말": "Ruins",
    "포스트": "Ruins",
    "좀비": "Wasteland",
    "zombie": "Wasteland",
    "황무지": "Wasteland",
    "마왕": "Night",
    "dark": "Night",
    "어둠": "Night",
    "암흑": "Night",
    "성": "Mansion",
    "castle": "Mansion",
    "저택": "Mansion",
    "하늘": "Sky",
    "sky": "Sky",
    "구름": "Sky",
    "비행": "FlyingIsland",
    "마을": "Town1",
    "town": "Town1",
    "협곡": "Canyon",
    "canyon": "Canyon",
    "황금": "Gold",
    "gold": "Gold",
    "보물": "Gold",
    "프리렌": "Monument",
    "여행": "Monument",
}

_TITLE_BGM_KEYWORDS: dict[str, str] = {
    "판타지": "Theme4",
    "중세": "Theme4",
    "기사": "Theme4",
    "sf": "Theme5",
    "우주": "Theme5",
    "사이버": "Theme5",
    "좀비": "Theme3",
    "어둠": "Theme3",
    "마왕": "Theme3",
    "해적": "Theme2",
    "바다": "Theme2",
}


def _select_title_assets(theme: str) -> tuple[str, str, str]:
    """GameSpec.theme → (title1Name, title2Name, titleBgm 이름)."""
    theme_lower = theme.lower()

    # title1Name: 키워드 매칭
    title1 = "Sword"  # fallback
    for keyword, bg in _TITLE_BG_KEYWORDS.items():
        if keyword in theme_lower:
            title1 = bg
            break

    # title2Name: SF/현대 → Floral, 판타지/중세 → Medieval
    sf_keywords = {"sf", "우주", "사이버", "좀비", "현대", "미래", "로봇"}
    title2 = "Floral" if any(k in theme_lower for k in sf_keywords) else "Medieval"

    # titleBgm
    bgm = "Theme6"  # fallback
    for keyword, music in _TITLE_BGM_KEYWORDS.items():
        if keyword in theme_lower:
            bgm = music
            break

    return title1, title2, bgm


def build_ending_common_event(switch_id: int, ending_lines: list[str]) -> dict:
    """보스 처치 시 자동 실행되는 엔딩 CommonEvent."""
    cmds: list[dict] = []
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})  # Wait 1초
    for line in ending_lines:
        cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]})
        cmds.append({"code": 401, "indent": 0, "parameters": [line]})
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})
    cmds.append({"code": 221, "indent": 0, "parameters": []})  # Fadeout
    cmds.append({"code": 230, "indent": 0, "parameters": [60]})
    cmds.append({"code": 354, "indent": 0, "parameters": []})  # Return to Title
    cmds.append({"code": 0, "indent": 0, "parameters": []})

    return {
        "id": 1,
        "name": "엔딩",
        "switchId": switch_id,
        "trigger": 1,  # Autorun
        "list": cmds,
    }


def build_system_json_phase2(
    game_spec: GameSpec,
    id_table: IdTable,
    switch_table: SwitchTable,
    start_map_id: int | None = None,
    start_x: int = 0,
    start_y: int = 0,
) -> dict:
    """System.json 조립. startMapId/startX/Y는 호출자가 결정."""
    party_members = sorted(id_table.actors.values())
    map_id = start_map_id if start_map_id is not None else min(id_table.maps.values(), default=1)

    title1, title2, title_bgm = _select_title_assets(game_spec.theme)

    return {
        "gameTitle": game_spec.title,
        "locale": "ko_KR",
        "currencyUnit": "G",
        "startMapId": map_id,
        "startX": start_x,
        "startY": start_y,
        "partyMembers": party_members,
        "switches": switch_table.to_rpgmaker_switches(),
        "variables": switch_table.to_rpgmaker_variables(),
        "elements": [None, "물리", "화염", "냉기", "번개", "성", "암흑"],
        "skillTypes": [None, "마법", "필살기"],
        "weaponTypes": [None, "단검", "검", "도끼", "지팡이", "활"],
        "armorTypes": [None, "일반방어구", "마법방어구", "장신구"],
        "equipTypes": [None, "무기", "방패", "투구", "갑옷", "장신구"],
        "magicSkills": [1],
        "menuCommands": [True, True, True, True, True, True],
        "optDisplayTp": False,
        "optDrawTitle": True,
        "optExtraExp": False,
        "optFloorDeath": False,
        "optFollowers": True,
        "optSideView": False,
        "optSlipDeath": False,
        "optTransparent": False,
        "versionId": 1,
        "editMapId": min(id_table.maps.values(), default=1),
        "battleBgm": _audio("Battle1"),
        "defeatMe": _audio("Defeat1"),
        "gameoverMe": _audio("Gameover1"),
        "titleBgm": _audio(title_bgm),
        "victoryMe": _audio("Victory1"),
        "title1Name": title1,
        "title2Name": title2,
        "battleback1Name": "",
        "battleback2Name": "",
        "battlerName": "",
        "battlerHue": 0,
        "sounds": _default_sounds(),
        "attackMotions": _default_attack_motions(),
        "terms": _default_terms(),
        "airship": _default_vehicle(),
        "boat": _default_vehicle(),
        "ship": _default_vehicle(),
        "testBattlers": [],
        "testTroopId": 1,
        "windowTone": [0, 0, 0, 0],
        # RPG Maker MZ 1.6+ 필수 필드
        "itemCategories": [True, True, True, True],
        "battleSystem": 0,
        "optAutosave": True,
        "optMessageSkip": True,
        "optSplashScreen": False,
        "optKeyItemsNumber": False,
        "iconSize": 32,
        "faceSize": 144,
        "tileSize": 48,
        "titleCommandWindow": {"background": 0, "offsetX": 0, "offsetY": 0},
        "advanced": {
            "gameId": 72894844,
            "screenWidth": 816,
            "screenHeight": 624,
            "uiAreaWidth": 816,
            "uiAreaHeight": 624,
            "numberFontFilename": "mplus-2p-bold-sub.woff",
            "fallbackFonts": "Malgun Gothic, Apple SD Gothic Neo, sans-serif",
            "fontSize": 26,
            "mainFontFilename": "",
            "screenScale": 1,
            "windowOpacity": 192,
            "picturesUpperLimit": 100,
        },
        "editor": {"messageWidth1": 60, "messageWidth2": 47, "jsonFormatLevel": 1},
    }


def build_map_infos(map_specs: list[MapSpec], id_table: IdTable) -> list:
    """MapInfos.json 배열 조립 (RPG Maker MZ 표준: [null, {id:1,...}, {id:2,...}])."""
    max_id = 0
    entries: dict[int, dict] = {}
    for order, spec in enumerate(map_specs, start=1):
        # spec.map_id 직접 사용 — id_table 이름 조회 시 None 반환으로 맵 누락되는 버그 방지
        map_id = spec.map_id
        entries[map_id] = {
            "id": map_id,
            "expanded": order == 1,
            "name": spec.name,
            "order": order,
            "parentId": 0,
            "scrollX": 0,
            "scrollY": 0,
        }
        if map_id > max_id:
            max_id = map_id
    result: list = [None] * (max_id + 1)
    for map_id, entry in entries.items():
        result[map_id] = entry
    return result


# 맵 타입별 안전한 BGM 기본값 (audio/bgm/ 폴더에 실제 존재하는 파일)
_SAFE_BGM: dict[str, str] = {
    "town": "Town1",
    "dungeon": "Dungeon1",
    "boss": "Battle1",
    "field": "Field1",
}

# 실제 존재하는 BGM 파일 목록 (확장자 제외)
_VALID_BGM: frozenset[str] = frozenset(
    [
        "Battle1",
        "Battle2",
        "Battle3",
        "Battle4",
        "Battle5",
        "Battle6",
        "Battle7",
        "Battle8",
        "Castle1",
        "Castle2",
        "Dungeon1",
        "Dungeon2",
        "Dungeon3",
        "Dungeon4",
        "Dungeon5",
        "Dungeon6",
        "Dungeon7",
        "Field1",
        "Field2",
        "Field3",
        "Field4",
        "Scene1",
        "Scene2",
        "Scene3",
        "Scene4",
        "Scene5",
        "Scene6",
        "Scene7",
        "Scene8",
        "Scene9",
        "Ship1",
        "Ship2",
        "Ship3",
        "Theme1",
        "Theme2",
        "Theme3",
        "Theme4",
        "Theme5",
        "Theme6",
        "Town1",
        "Town2",
        "Town3",
        "Town4",
        "Town5",
        "Town6",
        "Town7",
        "Town8",
    ]
)


def _resolve_bgm(spec: MapSpec) -> str:
    """BGM 이름이 유효하지 않으면 맵 타입별 기본값으로 대체."""
    if spec.bgm in _VALID_BGM:
        return spec.bgm
    fallback = _SAFE_BGM.get(spec.map_type, "Town1")
    logger.warning(
        "Map%d('%s') bgm='%s' — 존재하지 않는 파일, '%s'로 대체",
        spec.map_id,
        spec.name,
        spec.bgm,
        fallback,
    )
    return fallback


def _build_encounter_list(spec: MapSpec, events: list[dict]) -> list[dict]:
    """랜덤 인카운터 목록 — 항상 빈 배열 반환.

    전투는 이벤트 기반(BattleEvent)으로만 진행하며, 랜덤 인카운터는 사용하지 않음.
    """
    return []


def build_map_json(spec: MapSpec, tile_data: list[int], events: list[dict]) -> dict:
    """Map00N.json 단일 맵 파일 조립."""
    encounter_list = _build_encounter_list(spec, events)
    bgm_name = _resolve_bgm(spec)

    return {
        "autoplayBgm": bool(bgm_name),
        "autoplayBgs": False,
        "battleback1Name": "",
        "battleback2Name": "",
        "bgm": {"name": bgm_name, "pan": 0, "pitch": 100, "volume": 90},
        "bgs": {"name": "", "pan": 0, "pitch": 100, "volume": 90},
        "data": tile_data,
        "displayName": spec.name,
        "disableDashing": False,
        "encounterList": encounter_list,
        "encounterStep": 30,
        "events": [None] + events,  # index-0 null 규칙
        "height": spec.height,
        "note": "",
        "parallaxLoopX": False,
        "parallaxLoopY": False,
        "parallaxName": "",
        "parallaxShow": True,
        "parallaxSx": 0,
        "parallaxSy": 0,
        "scrollType": 0,
        "specifyBattleback": False,
        "tilesetId": spec.tileset_id,
        "width": spec.width,
    }


def translate_map_ids(
    map_json: dict,
    id_mapping: dict[int, int],
    map_specs: list[MapSpec] | None = None,
    map_tiles: dict[int, list[int]] | None = None,
    tilesets: list | None = None,
) -> dict:
    """맵 JSON 내부의 '장소 이동(201)' 이벤트 목적지 ID를 새 번호로 번역 및 좌표 보정.

    1. ID 번역: 삭제된 맵(1~5번) 참조를 이번 게임에서 생성된 유효한 ID로 변경.
    2. 좌표 보정: 이동 목적지가 통행 불가능한 타일(물 등)인 경우 근처 안전한 타일로 수정.
    """
    if not id_mapping:
        return map_json

    # 리다이렉션할 기본 목적지 후보들 (ID 리스트)
    valid_ids = sorted(id_mapping.values())
    fallback_id = valid_ids[0]  # 기본값: 첫 번째 맵

    events = map_json.get("events", [])
    for event in events:
        if event is None:
            continue
        pages = event.get("pages", [])
        for page in pages:
            list_commands = page.get("list", [])
            for cmd in list_commands:
                # 코드 201: 장소 이동 (Transfer Player)
                if cmd.get("code") == 201:
                    params = cmd.get("parameters", [])
                    if len(params) > 1 and params[0] == 0:  # 0: 직접 지정 방식
                        # 1. 맵 ID 번역
                        old_map_id = params[1]
                        if old_map_id in id_mapping:
                            params[1] = id_mapping[old_map_id]
                        else:
                            params[1] = fallback_id
                            logger.info(
                                "후처리 리다이렉션: 존재하지 않는 맵 참조 %d를 유효한 맵 %d로 변경했습니다.",
                                old_map_id,
                                fallback_id,
                            )

                        # 2. 좌표 안전성 체크 (룰베이스 후처리)
                        target_map_id = params[1]
                        target_x = params[2] if len(params) > 2 else 0
                        target_y = params[3] if len(params) > 3 else 0

                        if map_specs and map_tiles and tilesets:
                            target_spec = next(
                                (s for s in map_specs if s.map_id == target_map_id), None
                            )
                            target_data = map_tiles.get(target_map_id)

                            if target_spec and target_data:
                                # 비트연산 기반 통행성 체크 및 보정
                                new_x, new_y = find_nearest_safe_coord(
                                    target_data,
                                    target_x,
                                    target_y,
                                    target_spec.width,
                                    target_spec.height,
                                    target_spec.tileset_id,
                                    tilesets,
                                )

                                if (new_x, new_y) != (target_x, target_y):
                                    params[2], params[3] = new_x, new_y
                                    logger.info(
                                        "장소 이동(201) 좌표 보정: Map%d (%d,%d) -> (%d,%d) (안전 타일로 이동)",
                                        target_map_id,
                                        target_x,
                                        target_y,
                                        new_x,
                                        new_y,
                                    )
    return map_json


async def integrator(state: GenerationState) -> dict:
    """H 노드: 모든 중간 결과물 → RPG Maker MZ 프로젝트 파일 dict."""
    gen_id = state["generation_id"]
    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "integration",
            "progress": 88,
            "message": "프로젝트 파일 조립 중...",
        },
    )

    game_spec: GameSpec = state["game_spec"]  # type: ignore[assignment]
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    switch_table: SwitchTable = state["switch_table"]  # type: ignore[assignment]
    assets: dict[str, Any] = state.get("generated_assets", {})
    map_specs: list[MapSpec] = state.get("map_specs", [])
    map_tiles: dict[int, list[int]] = state.get("map_tiles", {})
    compiled_events: dict[int, list[dict]] = state.get("compiled_events", {})

    final_project: dict[str, Any] = {}

    # 1. 에셋 파일 그대로 복사
    for fname in [
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "Troops.json",
    ]:
        if fname in assets:
            final_project[fname] = assets[fname]

    # 4. base_game에서 상속받는 고정 파일들 로드 (tilesets를 먼저 확보)
    final_project["States.json"] = _load_base_game_file("States.json")
    final_project["Animations.json"] = _load_base_game_file("Animations.json")
    # CommonEvents.json — 보스 처치 엔딩 CommonEvent 삽입
    common_events = _load_base_game_file("CommonEvents.json")
    boss_switch_id: int | None = None
    for enemy in game_spec.enemies:
        if enemy.tier == "boss":
            sw_name = normalize_switch_name(f"{enemy.name}_defeated")
            boss_switch_id = switch_table.switches.get(sw_name)
            if boss_switch_id is not None:
                break
    if boss_switch_id is not None:
        ending_lines = [
            f"{game_spec.title}의 이야기가 끝났습니다.",
            "플레이해 주셔서 감사합니다!",
        ]
        ending_ce = build_ending_common_event(boss_switch_id, ending_lines)
        if isinstance(common_events, list) and len(common_events) > 1:
            common_events[1] = ending_ce
        elif isinstance(common_events, list):
            common_events.append(ending_ce)
    final_project["CommonEvents.json"] = common_events

    tilesets = load_base_tilesets()
    final_project["Tilesets.json"] = tilesets

    # 2. System.json — startPos: 첫 번째 town 맵의 walkable 타일 (BFS)
    start_map_id = min(id_table.maps.values(), default=1)
    start_x, start_y = 0, 0
    if map_specs and map_tiles:
        start_spec = next(
            (s for s in map_specs if s.map_type == "town"),
            map_specs[0],
        )
        start_map_id = start_spec.map_id
        tile_data = map_tiles.get(start_map_id)

        if tile_data:
            # 기존 좌표가 샘플 맵에서 왔든 LLM이 정했든,
            # Integrator 단계에서 실제 Tilesets.json flags를 기준으로 최종 재검증합니다.
            logger.info(
                "Integrator: 플레이어 시작 좌표 최종 검증 시작 (MapID: %d, Tilesets 유무: %s)",
                start_map_id,
                tilesets is not None,
            )
            start_x, start_y = calculate_spawn_point(start_spec, tile_data, tilesets=tilesets)
            logger.info("Integrator: 플레이어 시작 좌표 확정 (%d, %d)", start_x, start_y)
        else:
            # 타일 데이터가 없는 예외 케이스
            start_x, start_y = start_spec.spawn_point

    final_project["System.json"] = build_system_json_phase2(
        game_spec,
        id_table,
        switch_table,
        start_map_id=start_map_id,
        start_x=start_x,
        start_y=start_y,
    )

    # 3. MapInfos.json + Map*.json
    if map_specs:
        final_project["MapInfos.json"] = build_map_infos(map_specs, id_table)

        id_mapping: dict[int, int] = {}
        for spec in map_specs:
            if spec.original_file_name:
                try:
                    orig_id = int(spec.original_file_name.replace("Map", "").replace(".json", ""))
                    id_mapping[orig_id] = spec.map_id
                except ValueError:
                    continue

        for spec in map_specs:
            tile_data = map_tiles.get(spec.map_id, [0] * (spec.width * spec.height * 6))
            events = compiled_events.get(spec.map_id, [])
            fname = f"Map{spec.map_id:03d}.json"
            map_json = build_map_json(spec, tile_data, events)
            if id_mapping:
                map_json = translate_map_ids(
                    map_json,
                    id_mapping,
                    map_specs=map_specs,
                    map_tiles=map_tiles,
                    tilesets=tilesets,
                )

            # 캐릭터 에셋 이름 보정 (대소문자/기호 불일치 해결)
            map_json = fix_character_filenames(map_json)

            final_project[fname] = map_json
    else:
        final_project["MapInfos.json"] = {
            "1": {
                "id": 1,
                "expanded": True,
                "name": "시작 맵",
                "order": 1,
                "parentId": 0,
                "scrollX": 0,
                "scrollY": 0,
            }
        }

    logger.info("integrator 완료: %d개 파일", len(final_project))

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "integration",
            "summary": f"{len(final_project)}개 파일 조립 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("integration")
    return {"final_project": final_project, "completed_phases": completed}
