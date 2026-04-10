"""H 노드 — integrator: 모든 중간 결과물 → 완전한 RPG Maker MZ 프로젝트.

Phase 2: 에셋 파일만 조립 (Map*.json, System.json 완전체는 Phase 3+).
canonical: docs/The_world/integrator_assembly.md
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.H
"""

import json
import logging
from pathlib import Path
from typing import Any

from agent.generation.mapgen import calculate_spawn_point
from agent.generation.models import GameSpec, MapSpec
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

# ── base_game 고정 파일 로드 ────────────────────────────────────────────────

_BASE_GAME_DATA = Path(__file__).resolve().parents[3] / "storage" / "games" / "base_game" / "data"


def _load_base_game_file(fname: str) -> list | dict:
    """base_game/data/{fname}을 읽어 반환. 실패 시 [None] fallback."""
    path = _BASE_GAME_DATA / fname
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("base_game %s 로드 실패, [None] fallback: %s", fname, e)
        return [None]


# 기본 타일셋 3개 (마을/던전/필드)
_DEFAULT_TILESETS: list[Any] = [
    None,  # index-0 null
    {
        "id": 1,
        "name": "마을",
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
        "note": "",
    },
    {
        "id": 2,
        "name": "던전",
        "mode": 1,
        "tilesetNames": [
            "Dungeon_A1",
            "Dungeon_A2",
            "",
            "Dungeon_A4",
            "Dungeon_A5",
            "Dungeon_B",
            "Dungeon_C",
            "",
            "",
        ],
        "flags": [0] * 8192,
        "note": "",
    },
    {
        "id": 3,
        "name": "필드",
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
        "note": "",
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
        "titleBgm": _audio("Theme6"),
        "victoryMe": _audio("Victory1"),
        "title1Name": "",
        "title2Name": "",
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


async def integrator(state: GenerationState) -> dict:
    """H 노드: 모든 중간 결과물 → RPG Maker MZ 프로젝트 파일 dict.

    Phase 2: 에셋 + System.json + MapInfos.json(빈 맵)
    Phase 3: 에셋 + 맵 파일(Map*.json) + System.json(startPos 확정)
    """
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

    # 2. System.json — startPos: 첫 번째 town 맵의 walkable 타일 (BFS)
    start_map_id = min(id_table.maps.values(), default=1)
    start_x, start_y = 0, 0
    if map_specs and map_tiles:
        # town 타입 맵 우선, 없으면 첫 번째 맵 사용
        start_spec = next(
            (s for s in map_specs if s.map_type == "town"),
            map_specs[0],
        )
        start_map_id = start_spec.map_id
        tile_data = map_tiles.get(start_map_id)
        if tile_data:
            start_x, start_y = calculate_spawn_point(start_spec, tile_data)

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
        for spec in map_specs:
            tile_data = map_tiles.get(spec.map_id, [0] * (spec.width * spec.height * 6))
            events = compiled_events.get(spec.map_id, [])
            fname = f"Map{spec.map_id:03d}.json"
            final_project[fname] = build_map_json(spec, tile_data, events)
    else:
        # Phase 2: 빈 플레이스홀더 맵 1개
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

    # 4. base_game에서 상속받는 고정 파일 (States/Animations/CommonEvents)
    final_project["States.json"] = _load_base_game_file("States.json")
    final_project["Animations.json"] = _load_base_game_file("Animations.json")
    final_project["CommonEvents.json"] = _load_base_game_file("CommonEvents.json")
    final_project["Tilesets.json"] = _DEFAULT_TILESETS

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
