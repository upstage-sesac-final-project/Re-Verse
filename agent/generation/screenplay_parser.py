"""각본(screenplay) 파서 — LLM 각본 텍스트를 DSL 이벤트로 변환.

각본의 Scene별로 NPC, 전투, 이동, 상점 이벤트를 추출하고
스위치 체인을 자동 연결한다.
"""

import logging
import re
from dataclasses import dataclass, field

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    BattleOnWinAction,
    ChestEvent,
    NpcEvent,
    ShopEvent,
    ShopItem,
    TransferEvent,
)
from agent.generation.models import MapSpec
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import normalize_switch_name

logger = logging.getLogger(__name__)


# ── 파싱된 Scene 데이터 ──────────────────────────────────────────────────────


@dataclass
class ParsedNpc:
    name: str
    role: str = "가이드"
    first_meet: str = ""
    hint: str = ""
    reward: str = ""


@dataclass
class ParsedShop:
    name: str
    greeting: str = ""


@dataclass
class ParsedBattle:
    troop: str
    reward_item: str = ""


@dataclass
class ParsedBoss:
    troop: str
    before_dialogue: str = ""
    after_dialogue: str = ""


@dataclass
class ParsedTransfer:
    condition: str = ""
    blocked: str = ""
    target_map: str = ""


@dataclass
class ParsedScene:
    map_name: str
    background: str = ""
    npcs: list[ParsedNpc] = field(default_factory=list)
    shop: ParsedShop | None = None
    battles: list[ParsedBattle] = field(default_factory=list)
    boss: ParsedBoss | None = None
    transfer: ParsedTransfer | None = None


# ── 각본 텍스트 → ParsedScene 리스트 ────────────────────────────────────────


def parse_screenplay(text: str) -> list[ParsedScene]:
    """각본 텍스트를 Scene 리스트로 파싱."""
    scenes: list[ParsedScene] = []

    # Scene 분할
    scene_blocks = re.split(r"^##\s*Scene\s*\d+\s*:\s*", text, flags=re.MULTILINE)

    for block in scene_blocks[1:]:  # 첫 번째는 Scene 앞의 빈 텍스트
        lines = block.strip().split("\n")
        if not lines:
            continue

        map_name = lines[0].strip()
        scene = ParsedScene(map_name=map_name)

        i = 1
        while i < len(lines):
            line = lines[i].strip()

            # [배경: ...]
            if line.startswith("[배경:"):
                scene.background = line.strip("[]").replace("배경:", "").strip()

            # NPC 파싱
            elif line.startswith("NPC "):
                npc_match = re.match(r"NPC\s+(.+?)\s*\((.+?)\)\s*:", line)
                if npc_match:
                    name = npc_match.group(1).strip()
                    role = npc_match.group(2).strip()

                    if role == "상점":
                        shop = ParsedShop(name=name)
                        i += 1
                        while i < len(lines) and lines[i].strip().startswith(("인사:", "  ")):
                            ln = lines[i].strip()
                            if ln.startswith("인사:"):
                                shop.greeting = _extract_dialogue(ln, "인사:")
                            i += 1
                        scene.shop = shop
                        continue
                    else:
                        npc = ParsedNpc(name=name, role=role)
                        i += 1
                        while i < len(lines):
                            ln = lines[i].strip()
                            if ln.startswith("첫만남:"):
                                npc.first_meet = _extract_dialogue(ln, "첫만남:")
                            elif ln.startswith("진행중:"):
                                npc.hint = _extract_dialogue(ln, "진행중:")
                            elif ln.startswith("완료후:"):
                                npc.reward = _extract_dialogue(ln, "완료후:")
                            elif ln and not ln.startswith(" "):
                                break
                            i += 1
                        scene.npcs.append(npc)
                        continue

            # 전투 파싱
            elif line.startswith("전투:"):
                troop = line.replace("전투:", "").strip()
                reward = ""
                i += 1
                while i < len(lines) and lines[i].strip().startswith(("승리보상:", "  ")):
                    ln = lines[i].strip()
                    if ln.startswith("승리보상:"):
                        reward = ln.replace("승리보상:", "").strip()
                    i += 1
                scene.battles.append(ParsedBattle(troop=troop, reward_item=reward))
                continue

            # 보스전 파싱
            elif line.startswith("보스전:"):
                troop = line.replace("보스전:", "").strip()
                boss = ParsedBoss(troop=troop)
                i += 1
                while i < len(lines):
                    ln = lines[i].strip()
                    if ln.startswith("전투전:"):
                        boss.before_dialogue = _extract_dialogue(ln, "전투전:")
                    elif ln.startswith("승리후:"):
                        boss.after_dialogue = _extract_dialogue(ln, "승리후:")
                    elif ln and not ln.startswith(" "):
                        break
                    i += 1
                scene.boss = boss
                continue

            # "보스전 전:" / "보스전 후:" — LLM이 보스전 대사를 별도 줄로 작성한 경우
            elif line.startswith("보스전 전:") or line.startswith("보스전전:"):
                if scene.boss is None and scene.battles:
                    # 마지막 전투를 보스전으로 승격
                    last_battle = scene.battles.pop()
                    scene.boss = ParsedBoss(troop=last_battle.troop)
                if scene.boss:
                    scene.boss.before_dialogue = _extract_dialogue(
                        line, "보스전 전:" if "보스전 전:" in line else "보스전전:"
                    )

            elif line.startswith("보스전 후:") or line.startswith("보스전후:"):
                if scene.boss:
                    scene.boss.after_dialogue = _extract_dialogue(
                        line, "보스전 후:" if "보스전 후:" in line else "보스전후:"
                    )

            # 이동조건
            elif line.startswith("이동조건:"):
                transfer = ParsedTransfer()
                # "... 충족 시 → 다음 맵"
                arrow_match = re.search(r"→\s*(.+)", line)
                if arrow_match:
                    transfer.target_map = arrow_match.group(1).strip()
                transfer.condition = line.replace("이동조건:", "").strip()
                scene.transfer = transfer

            # 차단대사
            elif line.startswith("차단대사:"):
                if scene.transfer is None:
                    scene.transfer = ParsedTransfer()
                scene.transfer.blocked = _extract_dialogue(line, "차단대사:")

            i += 1

        scenes.append(scene)

    return scenes


def _extract_dialogue(line: str, prefix: str) -> str:
    """'prefix: "대사"' 형식에서 대사만 추출."""
    text = line.replace(prefix, "").strip()
    return text.strip('"').strip("'").strip()


# ── ParsedScene → DSL 이벤트 변환 ───────────────────────────────────────────


def scenes_to_dsl(
    scenes: list[ParsedScene],
    map_specs: list[MapSpec],
    id_table: IdTable,
) -> dict[int, list]:
    """ParsedScene 리스트를 맵별 DSL 이벤트로 변환."""
    result: dict[int, list] = {}
    used_positions: dict[int, set[tuple[int, int]]] = {}

    for scene_idx, scene in enumerate(scenes):
        # 맵 매칭
        spec = _find_map_spec(scene.map_name, map_specs)
        if spec is None:
            logger.warning("Scene '%s': 맵을 찾을 수 없음, 건너뜀", scene.map_name)
            continue

        map_id = spec.map_id
        prefix = normalize_switch_name(spec.name)
        used = used_positions.setdefault(map_id, set())
        events: list = []

        # ── NPC 이벤트 ──
        # 첫 번째 NPC가 대화하면 quest_accepted ON (town: 퀘스트 수락, 기타: 맵 진입 확인)
        for ni, npc in enumerate(scene.npcs):
            x, y = _safe_pos(spec.width, spec.height, used)
            quest_sw = f"{prefix}_quest_accepted"
            complete_sw = f"{prefix}_cleared"

            # 첫 번째 NPC만 set_switch (맵당 1회)
            npc_set_switch = quest_sw if ni == 0 else None

            events.append(
                NpcEvent(
                    type="npc",
                    name=npc.name,
                    x=x,
                    y=y,
                    dialogue=[npc.first_meet] if npc.first_meet else ["안녕하세요, 여행자님."],
                    set_switch=npc_set_switch,
                    hint_switch=quest_sw if npc.hint else None,
                    hint_dialogue=[npc.hint] if npc.hint else None,
                    condition_switch=complete_sw if npc.reward else None,
                    alt_dialogue=[npc.reward] if npc.reward else None,
                )
            )

        # ── 상점 이벤트 ──
        if scene.shop:
            x, y = _safe_pos(spec.width, spec.height, used)
            shop_items = _build_shop_items(id_table)
            events.append(
                ShopEvent(
                    type="shop",
                    name=scene.shop.name,
                    x=x,
                    y=y,
                    dialogue=scene.shop.greeting or "어서오세요!",
                    items=shop_items,
                )
            )

        # ── 전투 이벤트 ──
        for bi, battle in enumerate(scene.battles):
            x, y = _safe_pos(spec.width, spec.height, used)
            troop = _resolve_troop_name(battle.troop, id_table)
            battle_sw = f"{prefix}_battle_{bi + 1}"
            win_sw = f"{prefix}_win_{bi + 1}"

            on_win = [BattleOnWinAction(set_switch=win_sw)]
            # 마지막 전투는 맵 클리어 스위치도 설정
            if bi == len(scene.battles) - 1:
                on_win.append(BattleOnWinAction(set_switch=f"{prefix}_cleared"))

            events.append(
                BattleEvent(
                    type="battle",
                    name=f"{troop.split('×')[0].split('_')[0]}_전투",
                    x=x,
                    y=y,
                    troop=troop,
                    battle_switch=battle_sw,
                    one_time=True,
                    on_win=on_win,
                )
            )

            # 보상 보물상자 (전투 승리 조건)
            if battle.reward_item and battle.reward_item != "없음":
                item_name, item_type = _resolve_item(battle.reward_item, id_table)
                if item_name:
                    cx, cy = _safe_pos(spec.width, spec.height, used)
                    events.append(
                        ChestEvent(
                            type="chest",
                            name=f"{prefix}_보물상자_{bi + 1}",
                            x=cx,
                            y=cy,
                            item=item_name,
                            item_type=item_type,
                            condition_switch=win_sw,
                            chest_switch=f"{prefix}_chest_{bi + 1}",
                            one_time=True,
                        )
                    )

        # ── 보스전 ──
        # boss 맵인데 scene.boss가 None이면 마지막 전투를 보스전으로 승격
        if scene.boss is None and spec.map_type == "boss" and scene.battles:
            last = scene.battles[-1]
            scene.boss = ParsedBoss(troop=last.troop)
            logger.info("boss 맵 '%s': 마지막 전투 '%s'를 보스전으로 승격", spec.name, last.troop)

        if scene.boss:
            x, y = _safe_pos(spec.width, spec.height, used)
            troop = _resolve_troop_name(scene.boss.troop, id_table)
            boss_name = troop.replace("_단독", "").replace("×1", "")
            defeated_sw = normalize_switch_name(f"{boss_name}_defeated")

            # 보스 전 NPC 대사
            if scene.boss.before_dialogue:
                nx, ny = _safe_pos(spec.width, spec.height, used)
                events.append(
                    NpcEvent(
                        type="npc",
                        name="수호자",
                        x=nx,
                        y=ny,
                        dialogue=[scene.boss.before_dialogue],
                        condition_switch=defeated_sw,
                        alt_dialogue=[scene.boss.after_dialogue or "평화가 찾아왔습니다!"],
                    )
                )

            events.append(
                BattleEvent(
                    type="battle",
                    name=f"보스전_{boss_name}",
                    x=x,
                    y=y,
                    troop=troop,
                    battle_switch=f"{prefix}_boss_battle",
                    one_time=True,
                    lose_condition="game_over",
                    escape_allowed=False,
                    on_win=[BattleOnWinAction(set_switch=defeated_sw)],
                )
            )

        # ── Transfer 이벤트 ──
        # 순방향(다음 맵)과 역방향(이전 맵)을 구분하여 게이트 적용
        forward_maps = {
            map_specs[si + 1].name
            for si in range(len(map_specs) - 1)
            if map_specs[si].map_id == spec.map_id
        }

        for exit_spec in spec.exits:
            ex, ey = _exit_pos(spec, exit_spec.direction)
            used.add((ex, ey))

            is_forward = exit_spec.label in forward_maps
            condition = None
            blocked = None

            if is_forward and scene.transfer and scene.transfer.blocked:
                # 순방향: 게이트 조건 적용 (전투 승리/퀘스트 완료 필요)
                if spec.map_type == "town":
                    condition = f"{prefix}_quest_accepted"
                else:
                    condition = f"{prefix}_cleared"
                blocked = scene.transfer.blocked

            # 목적지 좌표: 목적지 맵의 중앙 (범위 초과 방지)
            dest_spec = _find_map_spec(exit_spec.label, map_specs)
            dest_w = dest_spec.width if dest_spec else 30
            dest_h = dest_spec.height if dest_spec else 30
            to_x = min(dest_w // 2, dest_w - 2)
            to_y = min(dest_h // 2, dest_h - 2)

            events.append(
                TransferEvent(
                    type="transfer",
                    name=f"{exit_spec.label}_이동",
                    x=ex,
                    y=ey,
                    to_map=exit_spec.label,
                    to_x=to_x,
                    to_y=to_y,
                    condition_switch=condition,
                    blocked_dialogue=blocked,
                )
            )

        # 보스 맵 탈출 (exits 없으면)
        if not spec.exits and scene.boss:
            prev_map = map_specs[scene_idx - 1] if scene_idx > 0 else None
            if prev_map:
                ex, ey = _exit_pos(spec, "south")
                used.add((ex, ey))
                events.append(
                    TransferEvent(
                        type="transfer",
                        name=f"{prev_map.name}_탈출",
                        x=ex,
                        y=ey,
                        to_map=prev_map.name,
                        to_x=spec.width // 2,
                        to_y=spec.height // 2,
                    )
                )

        result[map_id] = events

    return result


# ── 헬퍼 ────────────────────────────────────────────────────────────────────


def _find_map_spec(scene_name: str, map_specs: list[MapSpec]) -> MapSpec | None:
    """Scene 이름으로 MapSpec 찾기."""
    for spec in map_specs:
        if spec.name in scene_name or scene_name in spec.name:
            return spec
    return None


def _safe_pos(w: int, h: int, used: set[tuple[int, int]]) -> tuple[int, int]:
    import random

    for _ in range(100):
        x = random.randint(2, w - 3)
        y = random.randint(2, h - 3)
        if (x, y) not in used:
            used.add((x, y))
            return x, y
    x, y = w // 2, h // 2
    while (x, y) in used:
        x += 1
    used.add((x, y))
    return x, y


def _exit_pos(spec: MapSpec, direction: str) -> tuple[int, int]:
    cx, cy = spec.width // 2, spec.height // 2
    return {
        "north": (cx, 1),
        "south": (cx, spec.height - 2),
        "east": (spec.width - 2, cy),
        "west": (1, cy),
    }.get(direction, (cx, cy))


def _resolve_troop_name(raw: str, id_table: IdTable) -> str:
    """각본의 적 이름을 id_table.troops의 정확한 키로 매칭."""
    if raw in id_table.troops:
        return raw
    # 부분 매칭
    raw_norm = normalize_switch_name(raw)
    for troop_name in id_table.troops:
        if normalize_switch_name(troop_name) == raw_norm:
            return troop_name
    # 이름에 포함된 troop 찾기
    for troop_name in id_table.troops:
        if raw.split("×")[0].split("_")[0].strip() in troop_name:
            return troop_name
    # 단독 troop 찾기
    for troop_name in id_table.troops:
        if "_단독" in troop_name and raw.replace(" ", "_") in troop_name:
            return troop_name
    logger.warning("troop '%s' 매칭 실패, 그대로 사용", raw)
    return raw


def _build_shop_items(id_table: IdTable) -> list[ShopItem]:
    items = []
    for name in list(id_table.items.keys())[:3]:
        items.append(ShopItem(item=name, item_type="item"))
    for name in list(id_table.weapons.keys())[:2]:
        items.append(ShopItem(item=name, item_type="weapon"))
    return items[:5] or [ShopItem(item="회복 포션", item_type="item")]


def _resolve_item(raw: str, id_table: IdTable) -> tuple[str, str]:
    """각본의 아이템 이름을 id_table에서 찾기."""
    if raw in id_table.items:
        return raw, "item"
    if raw in id_table.weapons:
        return raw, "weapon"
    if raw in id_table.armors:
        return raw, "armor"
    # 부분 매칭
    for name in id_table.weapons:
        if raw in name or name in raw:
            return name, "weapon"
    for name in id_table.items:
        if raw in name or name in raw:
            return name, "item"
    # 폴백: 첫 번째 무기
    if id_table.weapons:
        return list(id_table.weapons.keys())[0], "weapon"
    return "", "item"
