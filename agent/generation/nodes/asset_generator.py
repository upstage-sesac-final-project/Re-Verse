import asyncio
import logging
from typing import Any

from pydantic import BaseModel

from agent.core.llm_client import invoke_llm
from agent.generation.prompts.asset_generator_prompt import (
    build_actors_prompt,
    build_armors_prompt,
    build_classes_prompt,
    build_enemies_prompt,
    build_items_prompt,
    build_skills_prompt,
    build_weapons_prompt,
)
from agent.generation.schemas import (
    ActorsList,
    ArmorsList,
    ClassesList,
    EnemiesList,
    ItemsList,
    RpgTroop,
    RpgTroopMember,
    SkillsList,
    WeaponsList,
)
from agent.generation.state import GenerationState
from agent.utils.game_data_io import read_game_json

logger = logging.getLogger(__name__)

# ── 직업 성장 곡선 ─────────────────────────────────────────
_ROLE_CURVES: dict[str, list[tuple[int, int]]] = {
    "warrior": [(400, 2000), (50, 200), (15, 80), (12, 60), (8, 40), (8, 40), (8, 35), (8, 35)],
    "mage": [(200, 800), (100, 500), (5, 30), (5, 25), (20, 120), (15, 80), (8, 35), (8, 35)],
    "healer": [(250, 900), (120, 600), (5, 25), (8, 40), (15, 90), (18, 100), (8, 35), (10, 50)],
    "rogue": [(300, 1000), (50, 200), (12, 70), (8, 45), (8, 40), (8, 40), (12, 60), (12, 60)],
}

_STYLE_KEYWORDS: dict[str, list[str]] = {
    "warrior": [
        "warrior",
        "전사",
        "검사",
        "기사",
        "파이터",
        "버서커",
        "팔라딘",
        "knight",
        "fighter",
        "berserker",
        "soldier",
        "용사",
        "무사",
        "군인",
    ],
    "mage": [
        "mage",
        "마법사",
        "위자드",
        "소서러",
        "마술사",
        "흑마법사",
        "wizard",
        "sorcerer",
        "warlock",
        "witch",
        "연금술사",
    ],
    "healer": [
        "healer",
        "성직자",
        "힐러",
        "수도사",
        "클레릭",
        "프리스트",
        "수녀",
        "cleric",
        "priest",
        "monk",
        "bishop",
        "백마법사",
        "샤먼",
    ],
    "rogue": [
        "rogue",
        "도적",
        "닌자",
        "어쌔신",
        "레인저",
        "궁수",
        "탐정",
        "thief",
        "ninja",
        "assassin",
        "ranger",
        "archer",
        "hunter",
        "해커",
    ],
}


def _infer_curve_type(combat_style: str) -> str:
    s = combat_style.lower()
    for curve_type, keywords in _STYLE_KEYWORDS.items():
        if any(kw in s for kw in keywords):
            return curve_type
    return "warrior"


def _build_class_params(combat_style: str, levels: int = 99) -> list[list[int]]:
    curve_type = _infer_curve_type(combat_style)
    curves = _ROLE_CURVES[curve_type]
    return [
        [round(base + (final - base) * i / (levels - 1)) for i in range(levels)]
        for base, final in curves
    ]


async def asset_generator_node(state: GenerationState) -> GenerationState:
    """C. 에셋 생성 노드: LLM 병렬 호출로 에셋 데이터 생성."""
    logger.info("--- NODE: asset_generator ---")
    game_spec = state.get("game_spec")
    id_table_dict = state.get("id_table")

    if game_spec is None or id_table_dict is None:
        raise ValueError("game_spec or id_table is missing in state")

    results = await asyncio.gather(
        _generate_asset(build_skills_prompt(game_spec, id_table_dict), SkillsList, "Skills"),
        _generate_asset(build_items_prompt(game_spec, id_table_dict), ItemsList, "Items"),
        _generate_asset(build_weapons_prompt(game_spec, id_table_dict), WeaponsList, "Weapons"),
        _generate_asset(build_armors_prompt(game_spec, id_table_dict), ArmorsList, "Armors"),
        _generate_asset(build_enemies_prompt(game_spec, id_table_dict), EnemiesList, "Enemies"),
        _generate_asset(build_classes_prompt(game_spec, id_table_dict), ClassesList, "Classes"),
        return_exceptions=True,
    )

    assets: dict[str, Any] = {}
    fnames = [
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "Classes.json",
    ]

    for fname, result in zip(fnames, results):
        if isinstance(result, Exception) or result is None:
            logger.error("%s 생성 실패, base_game 데이터로 대체: %s", fname, result)
            assets[fname] = read_game_json("base_game", fname) or [None]
        else:
            assets[fname] = result

    # Classes.json 후처리
    processed_classes: list[Any] = [None]
    for cls_item in assets["Classes.json"][1:]:
        if cls_item is None:
            continue
        combat_style = cls_item.pop("combat_style", "warrior")
        cls_item["params"] = _build_class_params(combat_style)
        cls_item["expParams"] = [30, 20, 30, 30]
        processed_classes.append(cls_item)
    assets["Classes.json"] = processed_classes

    # Actors.json (의존성 에셋)
    try:
        assets["Actors.json"] = await _generate_asset(
            build_actors_prompt(game_spec, id_table_dict, assets["Classes.json"]),
            ActorsList,
            "Actors",
        )
    except Exception as e:
        logger.error("Actors.json 생성 실패, base_game 데이터로 대체: %s", e)
        assets["Actors.json"] = read_game_json("base_game", "Actors.json") or [None]

    # Troops
    assets["Troops.json"] = _generate_troops_locally(game_spec, id_table_dict)

    return {
        **state,
        "generated_assets": assets,
        "completed_phases": state.get("completed_phases", []) + ["assets"],
        "current_phase": "assets",
    }


async def _generate_asset(
    messages: list[Any], schema: type[BaseModel], category: str, max_attempts: int = 2
) -> list[Any]:
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            result = await invoke_llm(messages, structured_output=schema)
            items: list[Any] = getattr(result, "items", [])
            if not items or items[0] is not None:
                items = [None] + [i for i in items if i is not None]
            return [i.model_dump() if i is not None else None for i in items]
        except Exception as e:
            last_exc = e
            logger.warning(
                "%s 생성 실패 (시도 %d/%d): %s",
                category,
                attempt + 1,
                max_attempts,
                type(e).__name__,
            )
    raise last_exc if last_exc else RuntimeError(f"Failed to generate {category}")


def _generate_troops_locally(game_spec: dict[Any, Any], id_table: dict[Any, Any]) -> list[Any]:
    troops: list[Any] = [None]
    enemy_ids: dict[str, int] = id_table.get("enemies", {})
    troop_ids: dict[str, int] = id_table.get("troops", {})
    for enemy_name, enemy_id in enemy_ids.items():
        t_id = int(troop_ids.get(enemy_name, len(troops)))
        member = RpgTroopMember(enemyId=enemy_id, x=408, y=280)
        troop = RpgTroop(id=t_id, name=f"{enemy_name} 무리", members=[member])
        troops.append(troop.model_dump())
    return troops
