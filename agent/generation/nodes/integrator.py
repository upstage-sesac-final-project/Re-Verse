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
                logger.info("base_game에서 Tilesets.json 로드 성공 (ID 1-6)")
                return filtered
        except Exception as e:
            logger.error("base_game Tilesets.json 로드 실패: %s", e)

    # 2. 로드 실패 시 표준 폴백 (MZ 기본 구성)
    logger.warning("Tilesets.json 로드 실패 -> 표준 폴백 사용")
    return [
        None,
        {
            "id": 1,
            "name": "필드",
            "mode": 0,
            "tilesetNames": ["World_A1", "World_A2", "World_B", "World_C", "", "", "", "", ""],
            "flags": [0] * 8192,
            "note": "",
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
            "note": "",
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
            "note": "",
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
            "note": "",
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
            "note": "",
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
            "actorDamage": "%1은 %2의 데미지를 받았다!",
            "actorRecovery": "%1의 %2이(가) %3 회복됐다!",
            "actorGain": "%1의 %2이(가) %3 늘었다!",
            "actorLoss": "%1의 %2이(가) %3 줄었다!",
            "actorDrain": "%1의 %2이(가) %3 빼앗겼다!",
            "actorNoDamage": "%1은 데미지를 받지 않았다.",
            "actorNoHit": "미스!  %1은 데미지를 받지 않았다!",
            "enemyDamage": "%1에게 %2 데미지!",
            "enemyRecovery": "%1의 %2이(가) %3 회복됐다!",
            "enemyGain": "%1의 %2이(가) %3 늘었다!",
            "enemyLoss": "%1의 %2이(가) %3 줄었다!",
            "enemyDrain": "%2의 %3을(를) %1로부터 빼앗았다!",
            "enemyNoDamage": "%1은 데미지를 받지 않았다.",
            "enemyNoHit": "미스!  %1은 데미지를 받지 않았다!",
            "evasion": "%1은 공격을 회피했다!",
            "magicEvasion": "%1은 마법을 회피했다!",
            "magicReflection": "%1은 마법을 반사했다!",
            "counterAttack": "%1의 반격!",
            "substitute": "%1은 %2을 감쌌다!",
            "buffAdd": "%1의 %2이(가) 올랐다!",
            "debuffAdd": "%1의 %2이(가) 내려갔다!",
            "buffRemove": "%1의 %2이(가) 원래대로 돌아왔다.",
            "actionFailure": "%1에게는 효과가 없었다!",
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
        map_id = id_table.get_id("maps", spec.name)
        if map_id is None:
            continue
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


def build_map_json(spec: MapSpec, tile_data: list[int], events: list[dict]) -> dict:
    """Map00N.json 단일 맵 파일 조립."""
    # encounterList: town/boss → 빈 배열, dungeon/field → 기본 인카운터
    encounter_list: list[dict] = []
    if spec.map_type in ("dungeon", "field"):
        encounter_list = [
            {"troopId": 1, "weight": 10, "regionSet": []},
        ]

    return {
        "autoplayBgm": bool(spec.bgm),
        "autoplayBgs": False,
        "battleback1Name": "",
        "battleback2Name": "",
        "bgm": {"name": spec.bgm, "pan": 0, "pitch": 100, "volume": 90},
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


def translate_map_ids(map_json: dict, id_mapping: dict[int, int]) -> dict:
    """맵 JSON 내부의 '장소 이동(201)' 이벤트 목적지 ID를 새 번호로 번역."""
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
                    if len(params) > 1 and params[0] == 0:
                        old_map_id = params[1]
                        if old_map_id in id_mapping:
                            params[1] = id_mapping[old_map_id]
                            logger.debug(
                                "이벤트 ID 번역: Map %d -> %d",
                                old_map_id,
                                id_mapping[old_map_id],
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
                map_json = translate_map_ids(map_json, id_mapping)
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

    # 4. base_game에서 상속받는 고정 파일들
    final_project["States.json"] = _load_base_game_file("States.json")
    final_project["Animations.json"] = _load_base_game_file("Animations.json")
    final_project["CommonEvents.json"] = _load_base_game_file("CommonEvents.json")

    # Tilesets.json: base_game에서 가져온 표준 6종 데이터 사용
    final_project["Tilesets.json"] = load_base_tilesets()

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
