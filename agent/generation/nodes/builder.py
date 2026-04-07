"""Builder 노드 — GameBlueprint → RPG Maker MZ JSON 파일 생성 (LLM 없음)."""

import copy
import json
import logging
import shutil
from pathlib import Path

from agent.generation.balance.enemy_balance import (
    DIFFICULTY_MULTIPLIER,
    generate_enemy_params,
)
from agent.generation.balance.stat_templates import build_params_2d
from agent.generation.registry.id_table import IdTable
from agent.generation.schemas.game_blueprint import (
    ArmorBlueprint,
    EnemyBlueprint,
    GameBlueprint,
    ItemBlueprint,
    SkillBlueprint,
    TroopBlueprint,
    WeaponBlueprint,
)
from agent.generation.schemas.world_spec import WorldSpec
from agent.generation.state import GenerationState
from app.backend.core.config import settings
from app.backend.core.game_paths import get_game_data_path

logger = logging.getLogger(__name__)

EQUIP_SLOT_MAP = {"shield": 2, "head": 3, "body": 4, "accessory": 5}

# base_game에서 그대로 복사할 파일들
BASE_GAME_COPY_FILES = [
    "States.json",
    "Animations.json",
    "CommonEvents.json",
    "Tilesets.json",
]


async def builder_node(state: GenerationState) -> dict:
    """GameBlueprint → data/*.json 파일 생성."""
    game_id = state["game_id"]
    blueprint = GameBlueprint(**state["game_blueprint"])
    id_table = IdTable(**state["id_table"])
    world_spec = WorldSpec(**state["world_spec"])

    data_path = get_game_data_path(game_id)
    base_data_path = Path(settings.BASE_GAME_PATH).resolve() / "data"

    logger.info("[Builder] 시작: game_id=%s, data_path=%s", game_id, data_path)

    generated: list[str] = []
    errors: list[str] = []

    try:
        # ── base_game에서 정적 파일 복사 ──
        for fname in BASE_GAME_COPY_FILES:
            src = base_data_path / fname
            dst = data_path / fname
            if src.exists():
                shutil.copy2(src, dst)
                logger.debug("[Builder] 복사: %s", fname)

        # ── System.json ──
        system_json = _build_system_json(blueprint, base_data_path)
        _write_json(data_path / "System.json", system_json)
        generated.append("System.json")

        # ── Classes.json ──
        classes_json = _build_classes_json(blueprint)
        _write_json(data_path / "Classes.json", classes_json)
        generated.append("Classes.json")

        # ── Actors.json ──
        actors_json = _build_actors_json(blueprint)
        _write_json(data_path / "Actors.json", actors_json)
        generated.append("Actors.json")

        # ── Skills.json ──
        elements = blueprint.system.elements
        skills_json = _build_skills_json(blueprint, elements)
        _write_json(data_path / "Skills.json", skills_json)
        generated.append("Skills.json")

        # ── Items.json ──
        items_json = _build_items_json(blueprint)
        _write_json(data_path / "Items.json", items_json)
        generated.append("Items.json")

        # ── Weapons.json ──
        weapon_types = blueprint.system.weapon_types
        weapons_json = _build_weapons_json(blueprint, weapon_types)
        _write_json(data_path / "Weapons.json", weapons_json)
        generated.append("Weapons.json")

        # ── Armors.json ──
        armor_types = blueprint.system.armor_types
        armors_json = _build_armors_json(blueprint, armor_types)
        _write_json(data_path / "Armors.json", armors_json)
        generated.append("Armors.json")

        # ── Enemies.json ──
        enemies_json = _build_enemies_json(blueprint, id_table, world_spec.difficulty)
        _write_json(data_path / "Enemies.json", enemies_json)
        generated.append("Enemies.json")

        # ── Troops.json ──
        troops_json = _build_troops_json(blueprint)
        _write_json(data_path / "Troops.json", troops_json)
        generated.append("Troops.json")

        # ── MapInfos.json (맵 이름만 수정) ──
        map_infos_json = _build_map_infos_json(world_spec, base_data_path)
        _write_json(data_path / "MapInfos.json", map_infos_json)
        generated.append("MapInfos.json")

        # ── Map00X.json (각 맵 파일 생성) ──
        map_files = _build_map_files(world_spec, base_data_path, data_path)
        generated.extend(map_files)

        logger.info("[Builder] 완료: %d개 파일 생성", len(generated))

    except Exception as e:
        logger.error("[Builder] 오류: %s", e, exc_info=True)
        errors.append(str(e))

    return {
        "generated_files": generated,
        "build_errors": errors,
    }


# ── System.json ──────────────────────────────────────────────────────────────


def _build_system_json(blueprint: GameBlueprint, base_data_path: Path) -> dict:
    """base_game System.json의 정적 필드 + Blueprint 창작 필드 합성."""
    sys = blueprint.system

    # base_game System.json에서 정적 필드 로드
    base_system_path = base_data_path / "System.json"
    base_system: dict = {}
    if base_system_path.exists():
        with open(base_system_path, encoding="utf-8") as f:
            base_system = json.load(f)

    # base_game 정적 필드 복사 (창작 필드 제외)
    static_keys = [
        "advanced",
        "airship",
        "attackMotions",
        "battleBgm",
        "battleback1Name",
        "battleback2Name",
        "battlerHue",
        "battlerName",
        "battleSystem",
        "boat",
        "defeatMe",
        "editMapId",
        "equipTypes",
        "gameoverMe",
        "itemCategories",
        "magicSkills",
        "menuCommands",
        "optAutosave",
        "optDisplayTp",
        "optDrawTitle",
        "optExtraExp",
        "optFloorDeath",
        "optFollowers",
        "optKeyItemsNumber",
        "optSideView",
        "optSlipDeath",
        "optTransparent",
        "ship",
        "sounds",
        "switches",
        "terms",
        "testBattlers",
        "testTroopId",
        "title1Name",
        "title2Name",
        "titleBgm",
        "titleCommandWindow",
        "variables",
        "versionId",
        "victoryMe",
        "windowTone",
        "editor",
        "faceSize",
        "iconSize",
        "optSplashScreen",
        "optMessageSkip",
        "tileSize",
    ]
    result = {k: base_system[k] for k in static_keys if k in base_system}

    # 창작 필드 덮어쓰기
    result.update(
        {
            "gameTitle": sys.game_title,
            "locale": sys.locale,
            "currencyUnit": sys.currency_unit,
            "partyMembers": sys.party_members,
            "startMapId": sys.start_map_id,
            "startX": sys.start_x,
            "startY": sys.start_y,
            "skillTypes": sys.skill_types,
            "weaponTypes": sys.weapon_types,
            "armorTypes": sys.armor_types,
            "elements": sys.elements,
        }
    )

    return result


# ── Classes.json ─────────────────────────────────────────────────────────────


def _build_classes_json(blueprint: GameBlueprint) -> list:
    entries = []
    for bp in blueprint.classes:
        params_2d = build_params_2d(bp.role)
        entry = {
            "id": bp.id,
            "name": bp.name,
            "expParams": bp.exp_params,
            "params": params_2d,
            "traits": [],
            "learnings": [
                {"level": lrn.level, "skillId": lrn.skill_id, "note": "", "meta": {}}
                for lrn in bp.learnings
            ],
            "note": bp.note,
            "meta": {},
        }
        entries.append(entry)
    return build_json_array(entries)


# ── Actors.json ──────────────────────────────────────────────────────────────


def _build_actors_json(blueprint: GameBlueprint) -> list:
    entries = []
    for bp in blueprint.actors:
        # equips: [weapon, shield, head, body, accessory] = 5개
        equips = [bp.equip_weapon_id] + list(bp.equip_armor_ids[:4])
        while len(equips) < 5:
            equips.append(0)

        entry = {
            "id": bp.id,
            "name": bp.name,
            "classId": bp.class_id,
            "initialLevel": bp.initial_level,
            "maxLevel": bp.max_level,
            "faceIndex": max(0, min(7, bp.face_index)),
            "faceName": bp.face_name,
            "characterName": bp.character_name,
            "characterIndex": bp.character_index,
            "battlerName": bp.battler_name,
            "equips": equips,
            "traits": [],
            "profile": "",
            "nickname": "",
            "note": "",
            "meta": {},
        }
        entries.append(entry)
    return build_json_array(entries)


# ── Skills.json ──────────────────────────────────────────────────────────────


def _build_skills_json(blueprint: GameBlueprint, elements: list[str]) -> list:
    entries = []
    for bp in blueprint.skills:
        entry = _build_skill_entry(bp, elements)
        entries.append(entry)
    return build_json_array(entries)


def _build_skill_entry(bp: SkillBlueprint, elements: list[str]) -> dict:
    element_id = elements.index(bp.element) if bp.element in elements else 0
    # damage_type이 1,2 이면 공격 스킬 (hitType=2 마법), 3,4 이면 회복(hitType=0 확정)
    is_damage = bp.damage_type in (1, 2)
    hit_type = 2 if is_damage else 0

    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "stypeId": bp.skill_type_id,
        "mpCost": bp.mp_cost,
        "tpCost": bp.tp_cost,
        "scope": bp.scope,
        "occasion": bp.occasion,
        "animationId": -1,
        "iconIndex": 0,
        "damage": {
            "critical": False,
            "elementId": element_id,
            "formula": bp.formula,
            "type": bp.damage_type,
            "variance": 20,
        },
        "hitType": hit_type,
        "successRate": 100,
        "speed": 0,
        "repeats": 1,
        "tpGain": 0,
        "effects": [],
        "message1": "",
        "message2": "",
        "messageType": 0,
        "requiredWtypeId1": 0,
        "requiredWtypeId2": 0,
        "note": "",
        "meta": {},
    }


# ── Items.json ───────────────────────────────────────────────────────────────


def _build_items_json(blueprint: GameBlueprint) -> list:
    entries = []
    for bp in blueprint.items:
        entry = _build_item_entry(bp)
        entries.append(entry)
    return build_json_array(entries)


def _build_item_entry(bp: ItemBlueprint) -> dict:
    effects = []
    if bp.recover_hp_rate or bp.recover_hp_flat:
        effects.append(
            {
                "code": 11,
                "dataId": 0,
                "value1": bp.recover_hp_rate / 100,
                "value2": float(bp.recover_hp_flat),
            }
        )
    if bp.recover_mp_rate or bp.recover_mp_flat:
        effects.append(
            {
                "code": 12,
                "dataId": 0,
                "value1": bp.recover_mp_rate / 100,
                "value2": float(bp.recover_mp_flat),
            }
        )

    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "iconIndex": 0,
        "price": bp.price,
        "scope": bp.scope,
        "occasion": bp.occasion,
        "itypeId": 1,
        "consumable": True,
        "hitType": 0,
        "successRate": 100,
        "animationId": -1,
        "damage": {
            "critical": False,
            "elementId": 0,
            "formula": "0",
            "type": 0,
            "variance": 20,
        },
        "effects": effects,
        "speed": 0,
        "repeats": 1,
        "tpGain": 0,
        "note": "",
        "meta": {},
    }


# ── Weapons.json ─────────────────────────────────────────────────────────────


def _build_weapons_json(blueprint: GameBlueprint, weapon_types: list[str]) -> list:
    entries = []
    for bp in blueprint.weapons:
        entry = _build_weapon_entry(bp, weapon_types)
        entries.append(entry)
    return build_json_array(entries)


def _build_weapon_entry(bp: WeaponBlueprint, weapon_types: list[str]) -> dict:
    wtype_id = weapon_types.index(bp.weapon_type) if bp.weapon_type in weapon_types else 1
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "iconIndex": 0,
        "price": bp.price,
        "wtypeId": wtype_id,
        "etypeId": 1,
        "params": bp.params,
        "traits": [
            {"code": 31, "dataId": 1, "value": 0},
            {"code": 22, "dataId": 0, "value": 0},
        ],
        "animationId": 1,
        "note": "",
        "meta": {},
    }


# ── Armors.json ──────────────────────────────────────────────────────────────


def _build_armors_json(blueprint: GameBlueprint, armor_types: list[str]) -> list:
    entries = []
    for bp in blueprint.armors:
        entry = _build_armor_entry(bp, armor_types)
        entries.append(entry)
    return build_json_array(entries)


def _build_armor_entry(bp: ArmorBlueprint, armor_types: list[str]) -> dict:
    atype_id = armor_types.index(bp.armor_type) if bp.armor_type in armor_types else 1
    etype_id = EQUIP_SLOT_MAP.get(bp.equip_slot, 4)
    return {
        "id": bp.id,
        "name": bp.name,
        "description": bp.description,
        "iconIndex": 0,
        "price": bp.price,
        "atypeId": atype_id,
        "etypeId": etype_id,
        "params": bp.params,
        "traits": [],
        "note": "",
        "meta": {},
    }


# ── Enemies.json ─────────────────────────────────────────────────────────────


def _build_enemies_json(
    blueprint: GameBlueprint,
    id_table: IdTable,
    difficulty: str,
) -> list:
    entries = []
    for bp in blueprint.enemies:
        entry = _build_enemy_entry(bp, id_table, difficulty)
        entries.append(entry)
    return build_json_array(entries)


def _build_enemy_entry(
    bp: EnemyBlueprint,
    id_table: IdTable,
    difficulty: str,
) -> dict:
    params = generate_enemy_params(bp.tier, difficulty)
    mult = DIFFICULTY_MULTIPLIER.get(difficulty, DIFFICULTY_MULTIPLIER["normal"])

    # dropItems: 항상 정확히 3개
    KIND_MAP = {"item": 1, "weapon": 2, "armor": 3}
    drop_items = []
    for i in range(3):
        if i < len(bp.drop_items):
            d = bp.drop_items[i]
            kind = KIND_MAP.get(d.kind, 1)
            data_id = _resolve_drop_id(d, id_table)
            drop_items.append({"kind": kind, "dataId": data_id, "denominator": d.denominator})
        else:
            drop_items.append({"kind": 0, "dataId": 0, "denominator": 1})

    # actions
    actions = [
        {
            "skillId": sid,
            "conditionType": 0,
            "conditionParam1": 0,
            "conditionParam2": 0,
            "rating": 5,
        }
        for sid in bp.skill_ids
    ]

    return {
        "id": bp.id,
        "name": bp.name,
        "battlerName": bp.battler_name,
        "battlerHue": 0,
        "params": params,
        "exp": int(bp.exp * mult.get("exp", 1.0)),
        "gold": int(bp.gold * mult.get("gold", 1.0)),
        "dropItems": drop_items,
        "actions": actions,
        "traits": [],
        "note": "",
        "meta": {},
    }


def _resolve_drop_id(drop_spec, id_table: IdTable) -> int:
    try:
        if drop_spec.kind == "item":
            return id_table.items.get(drop_spec.name, 0)
        elif drop_spec.kind == "weapon":
            return id_table.weapons.get(drop_spec.name, 0)
        elif drop_spec.kind == "armor":
            return id_table.armors.get(drop_spec.name, 0)
    except Exception:
        pass
    return 0


# ── Troops.json ──────────────────────────────────────────────────────────────


def _build_troops_json(blueprint: GameBlueprint) -> list:
    entries = []
    for bp in blueprint.troops:
        entry = _build_troop_entry(bp)
        entries.append(entry)
    return build_json_array(entries)


def _build_troop_entry(bp: TroopBlueprint) -> dict:
    members = [{"enemyId": m.enemy_id, "x": m.x, "y": m.y, "hidden": False} for m in bp.members]
    return {
        "id": bp.id,
        "name": bp.name,
        "members": members,
        "pages": [
            {
                "conditions": {
                    "actorHp": 0,
                    "actorId": 1,
                    "actorValid": False,
                    "enemyHp": 0,
                    "enemyIndex": 0,
                    "enemyValid": False,
                    "switchId": 1,
                    "switchValid": False,
                    "turnA": 0,
                    "turnB": 0,
                    "turnEnding": False,
                    "turnValid": False,
                },
                "list": [{"code": 0, "indent": 0, "parameters": []}],
                "span": 0,
            }
        ],
    }


# ── MapInfos.json ────────────────────────────────────────────────────────────


def _build_map_infos_json(spec: WorldSpec, base_data_path: Path) -> list:
    """MapInfos.json: 맵 이름만 WorldSpec으로 대체, 나머지는 base_game 유지.
    RPG Maker MZ MapInfos.json은 list 형식 (index 0 = null).
    """
    base_path = base_data_path / "MapInfos.json"
    base_infos: list = [None]
    if base_path.exists():
        with open(base_path, encoding="utf-8") as f:
            base_infos = json.load(f)

    # spec.maps의 이름을 인덱스 순서대로 적용
    for i, map_info in enumerate(spec.maps, start=1):
        if i < len(base_infos) and base_infos[i] is not None:
            base_infos[i]["name"] = map_info.name
        else:
            # 배열 길이가 부족하면 확장
            while len(base_infos) <= i:
                base_infos.append(None)
            base_infos[i] = {
                "id": i,
                "name": map_info.name,
                "parentId": 0,
                "order": i,
                "expanded": False,
                "scrollX": 0,
                "scrollY": 0,
            }

    return base_infos


# ── Map files ────────────────────────────────────────────────────────────────


def _build_map_files(spec: WorldSpec, base_data_path: Path, data_path: Path) -> list[str]:
    """spec.maps 각각에 대한 Map00X.json 파일을 생성한다.
    Map001.json은 base_game에서 이미 복사됐으므로 displayName만 갱신.
    Map002.json 이후는 Map001.json을 템플릿으로 복사 생성.
    """
    base_map_path = base_data_path / "Map001.json"
    if not base_map_path.exists():
        logger.warning("[Builder] base Map001.json 없음 → 맵 파일 생성 건너뜀")
        return []

    with open(base_map_path, encoding="utf-8") as f:
        base_map = json.load(f)

    created = []
    for i, map_info in enumerate(spec.maps, start=1):
        map_filename = f"Map{i:03d}.json"
        dst = data_path / map_filename
        map_data = copy.deepcopy(base_map)
        map_data["displayName"] = map_info.name
        _write_json(dst, map_data)
        logger.debug("[Builder] 맵 파일 생성: %s (%s)", map_filename, map_info.name)
        created.append(map_filename)

    return created


# ── 공통 유틸 ────────────────────────────────────────────────────────────────


def build_json_array(items: list[dict]) -> list:
    """RPG Maker MZ JSON 배열: 인덱스 0은 null, id == 배열 인덱스."""
    result: list = [None]
    for item in sorted(items, key=lambda x: x["id"]):
        while len(result) < item["id"]:
            result.append(None)
        result.append(item)
    return result


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    logger.debug("[Builder] 작성: %s (%d bytes)", path.name, path.stat().st_size)
