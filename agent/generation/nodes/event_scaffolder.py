"""F-2 노드 — event_scaffolder: 맵 타입별 이벤트 뼈대 생성 (순수 코드, LLM 없음).

코드가 구조를 결정한다:
  - town: 퀘스트 NPC + 힌트 NPC + 상점 + 조건부 transfer
  - dungeon: 전투 2-3개 + 보물상자 + 힌트 NPC + 조건부 transfer
  - boss: 보스 전투 + NPC + 탈출 transfer (EndingEvent 없음)

대사 필드는 "_FILL_" placeholder로 채워지며, event_filler(LLM)가 후에 교체한다.

canonical: docs/The_world/event_redesign.md §event_scaffolder
"""

import logging
import random

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    BattleOnWinAction,
    ChestEvent,
    NpcEvent,
    ShopEvent,
    ShopItem,
    TransferEvent,
)
from agent.generation.models import (
    GameQuestPlan,
    GameSpec,
    MapQuestScript,
    MapSpec,
    Quest,
)
from agent.generation.progress import publish_progress
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import normalize_switch_name
from agent.generation.sprite_mapping import _build_troop_sprite_map, _fix_battle_sprites
from agent.generation.state import GenerationState

logger = logging.getLogger(__name__)

_FILL_ = "_FILL_"


# ── 좌표 유틸리티 ──────────────────────────────────────────────────────────


def _safe_coords(w: int, h: int, used: set[tuple[int, int]], margin: int = 2) -> tuple[int, int]:
    """맵 내 겹치지 않는 무작위 좌표 생성. margin만큼 가장자리 회피."""
    for _ in range(200):
        x = random.randint(margin, w - margin - 1)
        y = random.randint(margin, h - margin - 1)
        if (x, y) not in used:
            used.add((x, y))
            return x, y
    # 최악의 경우 중앙 근처에서 빈 칸 순차 탐색
    cx, cy = w // 2, h // 2
    for dx in range(-w // 2, w // 2):
        for dy in range(-h // 2, h // 2):
            nx, ny = cx + dx, cy + dy
            if margin <= nx < w - margin and margin <= ny < h - margin:
                if (nx, ny) not in used:
                    used.add((nx, ny))
                    return nx, ny
    # 정말 꽉 찬 경우 (이론적으로 발생하지 않음)
    used.add((cx, cy))
    return cx, cy


def _exit_coords(spec: MapSpec, direction: str) -> tuple[int, int]:
    """맵 가장자리의 exit 좌표. direction에 따라 적절한 위치 반환."""
    cx, cy = spec.width // 2, spec.height // 2
    coords: dict[str, tuple[int, int]] = {
        "north": (cx, 1),
        "south": (cx, spec.height - 2),
        "east": (spec.width - 2, cy),
        "west": (1, cy),
    }
    return coords.get(direction, (cx, 1))


# ── 맵 이름 → switch prefix ───────────────────────────────────────────────


def _prefix(map_name: str) -> str:
    return normalize_switch_name(map_name)


# ── 맵 타입별 스캐폴딩 ─────────────────────────────────────────────────────


def _scaffold_town(
    spec: MapSpec,
    map_script: MapQuestScript | None,
    quest: Quest | None,
    id_table: IdTable,
    quest_plan: GameQuestPlan | None = None,
) -> list[NpcEvent | TransferEvent | ShopEvent]:
    """town 맵 이벤트 뼈대 생성."""
    events: list = []
    used: set[tuple[int, int]] = set()
    prefix = _prefix(spec.name)

    # ── 퀘스트 NPC ──────────────────────────────────────────
    quest_npc_name = "촌장"
    completion_switch: str | None = None
    accept_switch = f"{prefix}_quest_accepted"

    if map_script and map_script.npcs:
        # 퀘스트 부여자 NPC 찾기
        quest_giver = next(
            (n for n in map_script.npcs if "퀘스트" in n.role or "부여" in n.role), None
        )
        if quest_giver:
            quest_npc_name = quest_giver.name

    if quest and quest.reward_switch:
        completion_switch = quest.reward_switch

    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(
        NpcEvent(
            type="npc",
            name=quest_npc_name,
            x=x,
            y=y,
            dialogue=[_FILL_],
            set_switch=accept_switch,
            condition_switch=completion_switch or f"{prefix}_cleared",
            alt_dialogue=[_FILL_],
        )
    )

    # ── 힌트 NPC ────────────────────────────────────────────
    hint_npc_name = "주민"
    if map_script:
        hint_npc = next((n for n in map_script.npcs if n.name != quest_npc_name), None)
        if hint_npc:
            hint_npc_name = hint_npc.name

    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(
        NpcEvent(
            type="npc",
            name=hint_npc_name,
            x=x,
            y=y,
            dialogue=[_FILL_],
            condition_switch=accept_switch,
            alt_dialogue=[_FILL_],
        )
    )

    # ── 상점 ────────────────────────────────────────────────
    shop_items: list[ShopItem] = []
    for item_name in list(id_table.items.keys())[:2]:
        shop_items.append(ShopItem(item="item", item_type="item"))
        shop_items[-1].item = item_name
    for weapon_name in list(id_table.weapons.keys())[:2]:
        shop_items.append(ShopItem(item=weapon_name, item_type="weapon"))

    if not shop_items:
        shop_items.append(ShopItem(item="포션", item_type="item"))

    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(
        ShopEvent(
            type="shop",
            name="상점 주인",
            x=x,
            y=y,
            dialogue=_FILL_,
            items=shop_items,
        )
    )

    # ── Transfer (exit별) ────────────────────────────────────
    for exit_spec in spec.exits:
        to_name = _resolve_map_name(exit_spec.to_map_id, id_table)
        if not to_name:
            continue

        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))

        # 목적지 맵의 gate_switch가 있으면 그것을 사용, 없으면 퀘스트 수락 조건
        gate_switch: str | None = None
        blocked_msg: str | None = None
        dest_map_name = exit_spec.label
        if quest_plan and dest_map_name:
            dest_script = _find_map_script_by_name(dest_map_name, quest_plan)
            if dest_script and dest_script.gate_switch:
                gate_switch = dest_script.gate_switch
                blocked_msg = _FILL_
        if not gate_switch and quest:
            gate_switch = accept_switch
            blocked_msg = _FILL_

        events.append(
            TransferEvent(
                type="transfer",
                name=f"{to_name} 이동",
                x=ex,
                y=ey,
                to_map=to_name,
                to_x=spec.width // 2,
                to_y=spec.height // 2,
                condition_switch=gate_switch,
                blocked_dialogue=blocked_msg,
            )
        )

    return events


def _select_troops_for_dungeon(id_table: IdTable, used_troops: set[str], num: int = 3) -> list[str]:
    """이미 사용된 troop을 제외하고 선택."""
    all_troops = [t for t in id_table.troops if "_단독" not in t]
    available = [t for t in all_troops if t not in used_troops]
    if not available:
        available = all_troops  # 전부 사용됐으면 리셋
    selected = available[:num]
    used_troops.update(selected)
    return selected


def _scaffold_dungeon(
    spec: MapSpec,
    map_script: MapQuestScript | None,
    quest: Quest | None,
    id_table: IdTable,
    used_troops: set[str] | None = None,
) -> list:
    """dungeon 맵 이벤트 뼈대 생성."""
    events: list = []
    used: set[tuple[int, int]] = set()
    prefix = _prefix(spec.name)

    if used_troops is None:
        used_troops = set()

    # ── 전투 이벤트 (2-3개) ─────────────────────────────────
    num_battles = random.randint(2, 3)
    battle_troops = _select_troops_for_dungeon(id_table, used_troops, num_battles)

    battle_switches: list[str] = []
    for i, troop_name in enumerate(battle_troops):
        b_switch = f"{prefix}_battle_{i + 1}"
        win_switch = f"{prefix}_battle_{i + 1}_won"
        battle_switches.append(win_switch)

        on_win_actions = [BattleOnWinAction(set_switch=win_switch)]

        # 마지막 전투는 cleared 스위치도 설정
        if i == len(battle_troops) - 1:
            cleared_switch = f"{prefix}_cleared"
            on_win_actions.append(BattleOnWinAction(set_switch=cleared_switch))

        x, y = _safe_coords(spec.width, spec.height, used)
        events.append(
            BattleEvent(
                type="battle",
                name=f"전투_{troop_name}",
                x=x,
                y=y,
                troop=troop_name,
                battle_switch=b_switch,
                on_win=on_win_actions,
            )
        )

    # ── 보물상자 (첫 전투 승리 조건) ────────────────────────
    act_index = map_script.act_index if map_script else 0
    chest_item = _pick_chest_item(id_table, act_index)
    chest_item_name, chest_item_type = chest_item

    first_win_switch = battle_switches[0] if battle_switches else None
    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(
        ChestEvent(
            type="chest",
            name="보물상자",
            x=x,
            y=y,
            item=chest_item_name,
            item_type=chest_item_type,
            chest_switch=f"{prefix}_chest_01",
            condition_switch=first_win_switch,
        )
    )

    # ── 힌트 NPC (map_script에 NPC가 있으면) ───────────────
    if map_script and map_script.npcs:
        npc_info = map_script.npcs[0]
        x, y = _safe_coords(spec.width, spec.height, used)
        events.append(
            NpcEvent(
                type="npc",
                name=npc_info.name,
                x=x,
                y=y,
                dialogue=[_FILL_],
                condition_switch=f"{prefix}_cleared",
                alt_dialogue=[_FILL_],
            )
        )

    # ── Transfer (exit별) ────────────────────────────────────
    cleared_switch = f"{prefix}_cleared"
    for exit_spec in spec.exits:
        to_name = _resolve_map_name(exit_spec.to_map_id, id_table)
        if not to_name:
            continue

        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))

        # south (뒤로) = 무조건, north (앞으로) = cleared 조건
        gate_switch: str | None = None
        blocked_msg: str | None = None
        if exit_spec.direction in ("north", "east"):
            gate_switch = cleared_switch
            blocked_msg = _FILL_

        events.append(
            TransferEvent(
                type="transfer",
                name=f"{to_name} 이동",
                x=ex,
                y=ey,
                to_map=to_name,
                to_x=spec.width // 2,
                to_y=spec.height // 2,
                condition_switch=gate_switch,
                blocked_dialogue=blocked_msg,
            )
        )

    return events


def _scaffold_boss(
    spec: MapSpec,
    map_script: MapQuestScript | None,
    boss_name: str,
    id_table: IdTable,
    quest_plan: GameQuestPlan | None = None,
) -> list:
    """boss 맵 이벤트 뼈대 생성. EndingEvent는 CommonEvent에서 처리하므로 여기서 생성하지 않는다."""
    events: list = []
    used: set[tuple[int, int]] = set()
    prefix = _prefix(spec.name)

    # ── 보스 troop 결정 ─────────────────────────────────────
    boss_troop = _find_boss_troop(boss_name, id_table)
    defeated_switch = f"{normalize_switch_name(boss_name)}_defeated"

    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(
        BattleEvent(
            type="battle",
            name=f"보스전_{boss_name}",
            x=x,
            y=y,
            troop=boss_troop,
            escape_allowed=False,
            battle_switch=f"{prefix}_boss_battle",
            on_win=[BattleOnWinAction(set_switch=defeated_switch)],
        )
    )

    # ── 보스 전 NPC ─────────────────────────────────────────
    npc_name = "수호자"
    if map_script and map_script.npcs:
        npc_name = map_script.npcs[0].name

    x, y = _safe_coords(spec.width, spec.height, used)
    events.append(
        NpcEvent(
            type="npc",
            name=npc_name,
            x=x,
            y=y,
            dialogue=[_FILL_],
            condition_switch=defeated_switch,
            alt_dialogue=[_FILL_],
        )
    )

    # ── 탈출 Transfer ───────────────────────────────────────
    for exit_spec in spec.exits:
        to_name = _resolve_map_name(exit_spec.to_map_id, id_table)
        if not to_name:
            continue

        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))

        events.append(
            TransferEvent(
                type="transfer",
                name=f"{to_name} 이동",
                x=ex,
                y=ey,
                to_map=to_name,
                to_x=spec.width // 2,
                to_y=spec.height // 2,
            )
        )

    # exits가 비어있으면 이전 맵으로 자동 탈출 transfer 추가
    if not spec.exits and quest_plan:
        prev_map_name = None
        for ms in quest_plan.maps:
            if ms.map_name == spec.name:
                break
            prev_map_name = ms.map_name
        if prev_map_name and prev_map_name in id_table.maps:
            x, y = _exit_coords(spec, "south")
            used.add((x, y))
            events.append(
                TransferEvent(
                    type="transfer",
                    name=f"{prev_map_name}_탈출",
                    x=x,
                    y=y,
                    to_map=prev_map_name,
                    to_x=spec.width // 2,
                    to_y=spec.height // 2,
                )
            )

    return events


# ── 헬퍼 ───────────────────────────────────────────────────────────────────


def _resolve_map_name(map_id: int, id_table: IdTable) -> str | None:
    """map_id → 맵 이름 역조회."""
    for name, mid in id_table.maps.items():
        if mid == map_id:
            return name
    return None


def _find_boss_troop(boss_name: str, id_table: IdTable) -> str:
    """보스 이름으로 troop 찾기. _단독 suffix 우선."""
    solo = f"{boss_name}_단독"
    if solo in id_table.troops:
        return solo
    # 이름이 포함된 troop 검색
    for troop_name in id_table.troops:
        if boss_name in troop_name:
            return troop_name
    # 최후의 수단: 마지막 troop
    if id_table.troops:
        return list(id_table.troops.keys())[-1]
    return boss_name


def _pick_chest_item(id_table: IdTable, act_index: int = 0) -> tuple[str, str]:
    """act_index에 따라 보물상자 아이템 선택. 진행할수록 좋은 아이템."""
    # 무기 → 방어구 → 아이템 순서로 우선
    all_weapons = list(id_table.weapons.keys())
    all_armors = list(id_table.armors.keys())
    all_items = list(id_table.items.keys())

    if all_weapons:
        idx = min(act_index, len(all_weapons) - 1)
        return all_weapons[idx], "weapon"
    if all_armors:
        idx = min(act_index, len(all_armors) - 1)
        return all_armors[idx], "armor"
    if all_items:
        return all_items[0], "item"
    return "회복 포션", "item"


def _find_quest_for_map(map_name: str, quest_plan: GameQuestPlan) -> Quest | None:
    """맵 이름과 관련된 퀘스트 찾기."""
    for quest in quest_plan.quests:
        for step in quest.steps:
            if step.map_name == map_name:
                return quest
    return None


def _find_map_script(map_id: int, quest_plan: GameQuestPlan) -> MapQuestScript | None:
    """quest_plan에서 map_id에 해당하는 MapQuestScript 찾기."""
    for ms in quest_plan.maps:
        if ms.map_id == map_id:
            return ms
    return None


def _find_map_script_by_name(map_name: str, quest_plan: GameQuestPlan) -> MapQuestScript | None:
    """quest_plan에서 맵 이름으로 MapQuestScript 찾기."""
    for ms in quest_plan.maps:
        if ms.map_name == map_name:
            return ms
    return None


# ── 메인 함수 ──────────────────────────────────────────────────────────────


def scaffold_map_events(
    map_spec: MapSpec,
    quest_plan: GameQuestPlan,
    id_table: IdTable,
    used_troops: set[str] | None = None,
) -> list:
    """단일 맵의 이벤트 뼈대 생성. 맵 타입에 따라 적절한 이벤트 조합 반환.

    Returns:
        list[DslEvent] — NpcEvent, BattleEvent, ChestEvent, ShopEvent, TransferEvent 혼합
    """
    map_script = _find_map_script(map_spec.map_id, quest_plan)
    quest = _find_quest_for_map(map_spec.name, quest_plan)

    if map_spec.map_type == "town":
        return _scaffold_town(map_spec, map_script, quest, id_table, quest_plan)
    elif map_spec.map_type == "dungeon":
        return _scaffold_dungeon(map_spec, map_script, quest, id_table, used_troops)
    elif map_spec.map_type == "boss":
        return _scaffold_boss(map_spec, map_script, quest_plan.boss_name, id_table, quest_plan)
    else:
        # field 등 — 최소 transfer만
        return _scaffold_field(map_spec, id_table)


def _scaffold_field(spec: MapSpec, id_table: IdTable) -> list:
    """field 맵: 최소 이벤트 (transfer + 최소 NPC 1명 보장)."""
    events: list = []
    used: set[tuple[int, int]] = set()
    for exit_spec in spec.exits:
        to_name = _resolve_map_name(exit_spec.to_map_id, id_table)
        if not to_name:
            continue
        ex, ey = _exit_coords(spec, exit_spec.direction)
        used.add((ex, ey))
        events.append(
            TransferEvent(
                type="transfer",
                name=f"{to_name} 이동",
                x=ex,
                y=ey,
                to_map=to_name,
                to_x=spec.width // 2,
                to_y=spec.height // 2,
            )
        )

    # 최소 이벤트 보장: transfer만 있으면 NPC 1명 추가
    non_transfer = [e for e in events if not isinstance(e, TransferEvent)]
    if not non_transfer:
        x, y = _safe_coords(spec.width, spec.height, used)
        events.append(
            NpcEvent(
                type="npc",
                name="여행자",
                x=x,
                y=y,
                dialogue=[_FILL_],
            )
        )

    return events


# ── Fallback quest plan ────────────────────────────────────────────────────


def _fallback_quest_plan(map_specs: list[MapSpec], id_table: IdTable) -> GameQuestPlan:
    """story_planner 실패 시 맵 순서 기반 기본 퀘스트 계획 생성.

    맵 순서를 act로 사용: town→dungeon→boss.
    """
    from agent.generation.models import NpcRole, QuestStep

    maps: list[MapQuestScript] = []
    steps: list[QuestStep] = []
    boss_name = "보스"

    # 보스 이름 결정: _단독 troop에서 추출
    for troop_name in id_table.troops:
        if troop_name.endswith("_단독"):
            boss_name = troop_name[: -len("_단독")]
            break

    for i, spec in enumerate(map_specs):
        prefix = _prefix(spec.name)

        npcs: list[NpcRole] = []
        gate_switch: str | None = None

        if spec.map_type == "town":
            npcs.append(NpcRole(name="촌장", role="퀘스트 부여자"))
            steps.append(
                QuestStep(
                    map_name=spec.name,
                    type="talk",
                    target="촌장",
                    description="퀘스트를 받는다",
                    completion_switch=f"{prefix}_quest_accepted",
                )
            )
        elif spec.map_type == "dungeon":
            gate_switch = _prev_town_switch(map_specs, i)
            troop = next((t for t in id_table.troops if not t.endswith("_단독")), None)
            if troop:
                steps.append(
                    QuestStep(
                        map_name=spec.name,
                        type="battle",
                        target=troop,
                        description="적을 처치한다",
                        completion_switch=f"{prefix}_cleared",
                    )
                )
        elif spec.map_type == "boss":
            gate_switch = _prev_dungeon_cleared(map_specs, i)

        maps.append(
            MapQuestScript(
                map_id=spec.map_id,
                map_name=spec.name,
                map_type=spec.map_type,
                act_index=i,
                npcs=npcs,
                gate_switch=gate_switch,
            )
        )

    quest = Quest(
        name="메인 퀘스트",
        steps=steps,
        reward_switch=f"{_prefix(map_specs[-1].name)}_cleared" if map_specs else None,
    )

    return GameQuestPlan(quests=[quest], maps=maps, boss_name=boss_name)


def _prev_town_switch(map_specs: list[MapSpec], current_idx: int) -> str | None:
    """현재 맵 이전의 town 맵에서 quest_accepted 스위치를 찾는다."""
    for i in range(current_idx - 1, -1, -1):
        if map_specs[i].map_type == "town":
            return f"{_prefix(map_specs[i].name)}_quest_accepted"
    return None


def _prev_dungeon_cleared(map_specs: list[MapSpec], current_idx: int) -> str | None:
    """현재 맵 이전의 dungeon 맵에서 cleared 스위치를 찾는다."""
    for i in range(current_idx - 1, -1, -1):
        if map_specs[i].map_type == "dungeon":
            return f"{_prefix(map_specs[i].name)}_cleared"
    return None


# ── LangGraph 워크플로우 노드 ──────────────────────────────────────────────


async def event_scaffolder(state: GenerationState) -> dict:
    """F-2 노드: 맵 타입별 이벤트 뼈대 생성.

    입력: map_specs, id_table, quest_plan (story_planner 출력)
    출력: event_skeletons (map_id → list[DslEvent])
    """
    gen_id = state["generation_id"]
    map_specs: list[MapSpec] = state.get("map_specs") or []
    id_table: IdTable = state["id_table"]  # type: ignore[assignment]
    quest_plan: GameQuestPlan | None = state.get("quest_plan")
    game_spec: GameSpec | None = state.get("game_spec")
    generated_assets: dict = state.get("generated_assets") or {}

    await publish_progress(
        gen_id,
        {
            "type": "progress",
            "phase": "event_scaffold",
            "progress": 63,
            "message": "이벤트 뼈대 생성 중...",
        },
    )

    # quest_plan이 없으면 fallback 생성
    if quest_plan is None:
        logger.warning("quest_plan 없음 → fallback 생성")
        quest_plan = _fallback_quest_plan(map_specs, id_table)

    # 스프라이트 매핑 사전 구성
    troop_to_sprite: dict[str, tuple[str, int]] = {}
    if game_spec is not None:
        troop_to_sprite = _build_troop_sprite_map(game_spec, id_table, generated_assets)

    event_skeletons: dict[int, list] = {}
    used_troops: set[str] = set()
    for spec in map_specs:
        try:
            events = scaffold_map_events(spec, quest_plan, id_table, used_troops)
            events = _fix_battle_sprites(events, troop_to_sprite)
            event_skeletons[spec.map_id] = events
            logger.info(
                "Map%d('%s') 스캐폴딩 완료: %d개 이벤트",
                spec.map_id,
                spec.name,
                len(events),
            )
        except Exception as e:
            logger.error("Map%d 스캐폴딩 실패: %s", spec.map_id, e)
            event_skeletons[spec.map_id] = []

    await publish_progress(
        gen_id,
        {
            "type": "phase_complete",
            "phase": "event_scaffold",
            "summary": f"{len(event_skeletons)}개 맵 이벤트 뼈대 생성 완료",
        },
    )

    completed = list(state.get("completed_phases", []))
    completed.append("event_scaffold")
    return {
        "event_skeletons": event_skeletons,
        "quest_plan": quest_plan,
        "completed_phases": completed,
    }
