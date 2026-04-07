"""Architect 노드 — 2차 LLM: WorldSpec + IdTable → GameBlueprint."""

import asyncio
import logging

from pydantic import SecretStr

from agent.core.config import agent_config
from agent.generation.prompts.architect_prompt import build_architect_prompt
from agent.generation.registry.id_table import IdTable
from agent.generation.schemas.game_blueprint import GameBlueprint
from agent.generation.schemas.world_spec import WorldSpec
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

ARCHITECT_MAX_TOKENS = 8192
ARCHITECT_TIMEOUT = 120.0

# tier별 기본 battler_name
TIER_DEFAULT_BATTLER = {
    "weak": "Slime",
    "normal": "Goblin",
    "elite": "Orc",
    "boss": "Darklord",
}


async def architect(state: GenerationState) -> dict:
    """WorldSpec + IdTable → GameBlueprint (창작 콘텐츠만 생성)."""
    spec = WorldSpec(**state["world_spec"])
    id_table = IdTable(**state["id_table"])
    asset_counts = state.get("asset_counts", {})
    retry_count = state.get("retry_count", 0)

    logger.info("[Architect] 시작: title='%s', retry=%d", spec.game_title, retry_count)

    messages = build_architect_prompt(spec, id_table, asset_counts)

    try:
        raw = await _call_llm(messages)
        logger.info("[Architect] LLM 응답 수신: %d chars", len(raw))
        logger.debug("[Architect] 응답 앞 300자: %s", raw[:300])

        # JSON 추출 → 구조 보정 → Pydantic 파싱
        data = _extract_json_dict(raw)
        data = _repair_blueprint_data(data, spec, id_table)
        blueprint = GameBlueprint.model_validate(data)

    except Exception as e:
        logger.error("[Architect] 실패: %s", e, exc_info=True)
        raise

    logger.info(
        "[Architect] 완료: classes=%d, actors=%d, skills=%d, enemies=%d",
        len(blueprint.classes),
        len(blueprint.actors),
        len(blueprint.skills),
        len(blueprint.enemies),
    )

    return {
        "game_blueprint": blueprint.model_dump(),
        "retry_count": retry_count,
    }


async def _call_llm(messages) -> str:
    """max_tokens 8192인 전용 LLM 인스턴스로 호출."""
    if "solar" in agent_config.LLM_MODEL.lower():
        from langchain_upstage import ChatUpstage

        llm = ChatUpstage(
            api_key=SecretStr(agent_config.LLM_API_KEY),
            model=agent_config.LLM_MODEL,
            temperature=agent_config.LLM_TEMPERATURE,
            max_tokens=ARCHITECT_MAX_TOKENS,
        )
    else:
        from langchain_openai import ChatOpenAI

        init_kwargs = {
            "api_key": SecretStr(agent_config.LLM_API_KEY),
            "model": agent_config.LLM_MODEL,
            "max_tokens": ARCHITECT_MAX_TOKENS,
            "temperature": agent_config.LLM_TEMPERATURE,
        }
        if agent_config.LLM_BASE_URL:
            init_kwargs["base_url"] = agent_config.LLM_BASE_URL
        llm = ChatOpenAI(**init_kwargs)

    logger.info(
        "[Architect] LLM 호출 시작 (max_tokens=%d, timeout=%.0fs)",
        ARCHITECT_MAX_TOKENS,
        ARCHITECT_TIMEOUT,
    )
    coro = llm.ainvoke(messages)
    response = await asyncio.wait_for(coro, timeout=ARCHITECT_TIMEOUT)
    return str(response.content)


def _extract_json_dict(text: str) -> dict:
    """응답 텍스트에서 JSON 객체를 추출한다."""
    import json
    import re

    code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if code_block:
        text = code_block.group(1).strip()
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start : end + 1]
        else:
            raise ValueError(f"JSON 블록을 찾을 수 없음. 응답 앞 200자: {text[:200]}")

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON 파싱 실패: {e}. 앞 200자: {text[:200]}") from e


def _repair_blueprint_data(data: dict, spec: WorldSpec, id_table: IdTable) -> dict:
    """LLM 응답의 구조적 문제를 IdTable 기반으로 자동 보정한다."""

    # ── 1. system 필드가 없으면 최상위 필드에서 구성 ──
    if "system" not in data:
        logger.warning("[Architect] 'system' 키 없음 → 최상위 필드로 재구성")
        actor_ids = list(id_table.actors.values())
        data["system"] = {
            "game_title": data.get("game_title", spec.game_title),
            "locale": data.get("locale", "ko_KR"),
            "currency_unit": data.get("currency_unit", spec.currency_name),
            "party_members": data.get("party_members", actor_ids),
            "start_map_id": data.get("start_map_id", 1),
            "start_x": data.get("start_x", 8),
            "start_y": data.get("start_y", 6),
            "skill_types": data.get("skill_types", ["", "마법", "필살기"]),
            "weapon_types": data.get("weapon_types", ["", "검", "지팡이", "단검", "활"]),
            "armor_types": data.get("armor_types", ["", "방어구", "마법 방어구"]),
            "elements": data.get(
                "elements", ["", "물리적", "불", "얼음", "천둥", "물", "흙", "바람", "빛", "어둠"]
            ),
        }

    # ── 2. system.party_members 없으면 IdTable에서 채우기 ──
    sys = data["system"]
    if not sys.get("party_members"):
        sys["party_members"] = list(id_table.actors.values())

    # ── 3. enemies: id/battler_name 없으면 IdTable에서 채우기 ──
    name_to_id = id_table.enemies  # {name: id}
    for enemy in data.get("enemies", []):
        if not isinstance(enemy, dict):
            continue
        # id 보정
        if not enemy.get("id"):
            enemy["id"] = name_to_id.get(enemy.get("name", ""), 0)
            if not enemy["id"]:
                # 이름으로 못 찾으면 순서대로
                idx = data["enemies"].index(enemy)
                enemy["id"] = idx + 1
        # battler_name 보정
        if not enemy.get("battler_name"):
            tier = enemy.get("tier", "normal")
            enemy["battler_name"] = TIER_DEFAULT_BATTLER.get(tier, "Slime")

    # ── 4. troops.members 가 int이면 → 해당 enemy_id 배열로 변환 ──
    for troop in data.get("troops", []):
        if not isinstance(troop, dict):
            continue
        members = troop.get("members")
        if isinstance(members, int):
            # 정수였으면 해당 troop id로 적 enemy_id 추정
            troop_id = troop.get("id", 1)
            enemy_id = _find_enemy_id_for_troop(troop_id, data.get("enemies", []))
            count = min(members, 3)
            troop["members"] = [
                {"enemy_id": enemy_id, "x": 400 + i * 100, "y": 400} for i in range(count)
            ]
        elif not members:
            troop_id = troop.get("id", 1)
            enemy_id = _find_enemy_id_for_troop(troop_id, data.get("enemies", []))
            troop["members"] = [{"enemy_id": enemy_id, "x": 400, "y": 400}]

    # ── 5. actors: 리소스 파일명이 잘못된 경우 보정 ──
    _VALID_FACE = {"Actor1", "Actor2", "Actor3", "People1", "Evil"}
    _VALID_BATTLER = {"Actor1_1", "Actor1_2", "Actor1_3", "Actor2_1", "Actor2_2", "Actor2_3"}
    _GENDER_FACE = {"male": "Actor1", "female": "Actor2"}
    _GENDER_BATTLER = {"male": "Actor1_1", "female": "Actor2_1"}
    name_to_gender = {m.name: m.gender for m in spec.party}

    for actor in data.get("actors", []):
        if not isinstance(actor, dict):
            continue
        gender = name_to_gender.get(actor.get("name", ""), "male")
        if actor.get("face_name") not in _VALID_FACE:
            actor["face_name"] = _GENDER_FACE.get(gender, "Actor1")
        if actor.get("character_name") not in _VALID_FACE:
            actor["character_name"] = _GENDER_FACE.get(gender, "Actor1")
        if actor.get("battler_name") not in _VALID_BATTLER:
            actor["battler_name"] = _GENDER_BATTLER.get(gender, "Actor1_1")

    # ── 6. classes.role 없으면 이름에서 추론 ──
    role_keywords = {
        "warrior": ["전사", "knight", "warrior", "fighter", "검사"],
        "mage": ["마법사", "mage", "wizard", "sorcerer", "마술사"],
        "healer": ["힐러", "healer", "성직자", "cleric", "priest"],
        "thief": ["도적", "thief", "rogue", "assassin", "도둑"],
        "archer": ["궁수", "archer", "ranger", "bow"],
    }
    for cls in data.get("classes", []):
        if not isinstance(cls, dict):
            continue
        if not cls.get("role"):
            name_lower = cls.get("name", "").lower()
            inferred = "default"
            for role, keywords in role_keywords.items():
                if any(kw in name_lower for kw in keywords):
                    inferred = role
                    break
            cls["role"] = inferred

    # ── 6. LLM이 통째로 빠뜨린 섹션 자동 채우기 ──
    data = _fill_missing_sections(data, spec, id_table)

    logger.debug(
        "[Architect] repair 완료: classes=%d, actors=%d, skills=%d, enemies=%d, troops=%d",
        len(data.get("classes", [])),
        len(data.get("actors", [])),
        len(data.get("skills", [])),
        len(data.get("enemies", [])),
        len(data.get("troops", [])),
    )
    return data


def _fill_missing_sections(data: dict, spec: WorldSpec, id_table: IdTable) -> dict:
    """LLM이 빠뜨린 섹션을 WorldSpec + IdTable 기반으로 자동 생성한다."""

    # role 추론 헬퍼
    role_map = {m.class_name: m.role for m in spec.party}
    seen_classes = list(dict.fromkeys(m.class_name for m in spec.party))

    # ── classes ──
    if not data.get("classes"):
        data["classes"] = [
            {
                "id": id_table.classes[cls],
                "name": cls,
                "role": role_map.get(cls, "default"),
                "exp_params": [30, 20, 30, 30],
                "learnings": _default_learnings(id_table, cls),
            }
            for cls in seen_classes
            if cls in id_table.classes
        ]

    # ── actors ──
    if not data.get("actors"):
        gender_battler = {"male": "Actor1_1", "female": "Actor2_1"}
        gender_face = {"male": "Actor1", "female": "Actor2"}
        data["actors"] = [
            {
                "id": id_table.actors[m.name],
                "name": m.name,
                "class_id": id_table.classes.get(m.class_name, 1),
                "face_name": gender_face.get(m.gender, "Actor1"),
                "face_index": i % 8,
                "character_name": gender_face.get(m.gender, "Actor1"),
                "character_index": i % 8,
                "battler_name": gender_battler.get(m.gender, "Actor1_1"),
            }
            for i, m in enumerate(spec.party)
            if m.name in id_table.actors
        ]

    # ── skills ──
    if not data.get("skills"):
        data["skills"] = _default_skills(id_table, seen_classes, role_map)

    # ── items ──
    if not data.get("items"):
        item_defaults = [
            {
                "id": id_table.items["HP포션(소)"],
                "name": "HP포션(소)",
                "price": 80,
                "scope": 7,
                "occasion": 0,
                "recover_hp_rate": 30,
                "recover_hp_flat": 20,
            },
            {
                "id": id_table.items["HP포션"],
                "name": "HP포션",
                "price": 150,
                "scope": 7,
                "occasion": 0,
                "recover_hp_rate": 50,
                "recover_hp_flat": 30,
            },
            {
                "id": id_table.items["MP포션(소)"],
                "name": "MP포션(소)",
                "price": 60,
                "scope": 7,
                "occasion": 0,
                "recover_mp_rate": 30,
                "recover_mp_flat": 0,
            },
            {
                "id": id_table.items["MP포션"],
                "name": "MP포션",
                "price": 120,
                "scope": 7,
                "occasion": 0,
                "recover_mp_rate": 50,
                "recover_mp_flat": 0,
            },
        ]
        data["items"] = [i for i in item_defaults if i["id"] > 0]

    # ── weapons ──
    if not data.get("weapons"):
        weapon_type_map = {
            "warrior": "검",
            "thief": "단검",
            "archer": "활",
            "mage": "지팡이",
            "healer": "지팡이",
            "default": "검",
        }
        data["weapons"] = [
            {
                "id": id_table.weapons[f"{cls}_무기"],
                "name": f"{cls}의 무기",
                "weapon_type": weapon_type_map.get(role_map.get(cls, "default"), "검"),
                "price": 100,
                "params": [0, 0, 10, 0, 0, 0, 0, 0],
            }
            for cls in seen_classes
            if f"{cls}_무기" in id_table.weapons
        ]

    # ── armors ──
    if not data.get("armors"):
        data["armors"] = [
            {
                "id": id_table.armors["방패"],
                "name": "방패",
                "armor_type": "방어구",
                "equip_slot": "shield",
                "price": 80,
                "params": [0, 0, 0, 5, 0, 0, 0, 0],
            },
            {
                "id": id_table.armors["갑옷"],
                "name": "갑옷",
                "armor_type": "방어구",
                "equip_slot": "body",
                "price": 120,
                "params": [0, 0, 0, 8, 0, 0, 0, 0],
            },
            {
                "id": id_table.armors["장신구"],
                "name": "장신구",
                "armor_type": "방어구",
                "equip_slot": "accessory",
                "price": 60,
                "params": [0, 0, 0, 2, 0, 2, 2, 0],
            },
        ]

    # ── enemies ──
    if not data.get("enemies"):
        data["enemies"] = [
            {
                "id": id_table.enemies[e.name],
                "name": e.name,
                "battler_name": TIER_DEFAULT_BATTLER.get(e.tier, "Slime"),
                "tier": e.tier,
                "exp": _tier_exp(e.tier),
                "gold": _tier_gold(e.tier),
                "drop_items": [],
                "skill_ids": [1],
            }
            for e in spec.enemies
            if e.name in id_table.enemies
        ]

    # ── troops ──
    if not data.get("troops"):
        data["troops"] = [
            {
                "id": id_table.troops.get(f"{e.name}_group", i + 1),
                "name": f"{e.name} 무리",
                "members": [{"enemy_id": id_table.enemies[e.name], "x": 400, "y": 400}],
            }
            for i, e in enumerate(spec.enemies)
            if e.name in id_table.enemies
        ]

    return data


def _default_learnings(id_table: IdTable, cls_name: str) -> list:
    """직업 고유 스킬 학습 목록 생성."""
    learnings = [{"level": 1, "skill_id": 1}]  # 공격 스킬
    skill_ids = [v for k, v in id_table.skills.items() if k.startswith(f"{cls_name}_skill_")]
    for i, sid in enumerate(skill_ids):
        learnings.append({"level": max(1, i * 5), "skill_id": sid})
    return learnings


def _default_skills(id_table: IdTable, seen_classes: list, role_map: dict) -> list:
    """기본 스킬 목록 생성."""
    skills = [
        {
            "id": 1,
            "name": "공격",
            "skill_type_id": 1,
            "mp_cost": 0,
            "scope": 1,
            "occasion": 1,
            "damage_type": 1,
            "element": "물리적",
            "formula": "a.atk * 2 - b.def",
        },
        {
            "id": 2,
            "name": "방어",
            "skill_type_id": 1,
            "mp_cost": 0,
            "scope": 11,
            "occasion": 1,
            "damage_type": 0,
            "element": "물리적",
            "formula": "0",
        },
    ]
    skill_templates = {
        "warrior": [
            ("강타", 1, "a.atk*3-b.def", 15),
            ("방패치기", 11, "0", 8),
            ("전투함성", 8, "a.atk*0.8-b.def", 12),
        ],
        "mage": [
            ("파이어볼", 1, "a.mat*2.5-b.mdf", 10),
            ("아이스볼", 1, "a.mat*2-b.mdf", 8),
            ("썬더", 2, "a.mat*1.2-b.mdf", 15),
            ("마력폭발", 1, "a.mat*3-b.mdf*0.5", 20),
        ],
        "healer": [
            ("힐", 7, "a.mat*1.5+50", 10),
            ("그룹힐", 8, "a.mat*0.8+30", 20),
            ("부활", 9, "a.mat+50", 15),
        ],
        "thief": [
            ("독찌르기", 1, "a.atk*1.5-b.def", 8),
            ("급소공격", 1, "a.atk*2.5-b.def*0.5", 12),
            ("숨기", 11, "0", 5),
        ],
        "default": [("특수공격", 1, "a.atk*2-b.def", 10), ("특수기술", 1, "a.atk*1.5-b.def", 8)],
    }
    for cls_name in seen_classes:
        role = role_map.get(cls_name, "default")
        tmpl = skill_templates.get(role, skill_templates["default"])
        for j, (sname, scope, formula, mp) in enumerate(tmpl):
            key = f"{cls_name}_skill_{j + 1}"
            if key in id_table.skills:
                skills.append(
                    {
                        "id": id_table.skills[key],
                        "name": sname,
                        "skill_type_id": 1,
                        "mp_cost": mp,
                        "scope": scope,
                        "occasion": 1,
                        "damage_type": 3 if scope in (7, 8, 9) else 1,
                        "element": "물리적",
                        "formula": formula,
                    }
                )
    return skills


def _tier_exp(tier: str) -> int:
    return {"weak": 30, "normal": 60, "elite": 200, "boss": 1000}.get(tier, 60)


def _tier_gold(tier: str) -> int:
    return {"weak": 15, "normal": 30, "elite": 100, "boss": 500}.get(tier, 30)


def _find_enemy_id_for_troop(troop_id: int, enemies: list) -> int:
    """troop_id와 같은 인덱스의 enemy_id 반환."""
    if 0 < troop_id <= len(enemies):
        e = enemies[troop_id - 1]
        if isinstance(e, dict):
            return e.get("id", troop_id)
    return troop_id
