"""EventCompiler — DSL → RPG Maker MZ 커맨드 변환.

canonical: docs/The_world/dsl_specification.md §컴파일러 구현 상세
canonical: docs/The_world/npc_conditional_and_shop.md
canonical: docs/The_world/game_ending_design.md
"""

import logging

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    ChestEvent,
    DslEvent,
    EndingEvent,
    NpcEvent,
    ShopEvent,
    TransferEvent,
)
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable

logger = logging.getLogger(__name__)

# goods_type: 0=item, 1=weapon, 2=armor
_ITEM_TYPE_TO_GOODS_CODE: dict[str, int] = {
    "item": 0,
    "weapon": 1,
    "armor": 2,
}

# direction → RPG Maker MZ 방향 코드
_DIRECTION_CODE: dict[str, int] = {
    "retain": 0,
    "down": 2,
    "left": 4,
    "right": 6,
    "up": 8,
}

# trigger → RPG Maker MZ trigger 코드
_TRIGGER_CODE: dict[str, int] = {
    "action_button": 0,
    "player_touch": 1,
    "event_touch": 2,
    "auto_run": 3,
    "parallel": 4,
}


class CompileError(Exception):
    """DSL 컴파일 오류."""


class EventCompiler:
    """DSL 이벤트를 RPG Maker MZ 이벤트 JSON으로 변환."""

    def __init__(self, id_table: IdTable, switch_table: SwitchTable) -> None:
        self.id_table = id_table
        self.switch_table = switch_table

    @property
    def final_switch_table(self) -> SwitchTable:
        return self.switch_table

    # ── ID 해석 ──────────────────────────────────────────────────────────────

    def resolve_map_id(self, name: str) -> int:
        if name not in self.id_table.maps:
            raise CompileError(f"맵 '{name}'을 id_table에서 찾을 수 없음")
        return self.id_table.maps[name]

    def resolve_item_id(self, name: str, item_type: str | None = None) -> int:
        """아이템 이름 → ID. item_type 지정 시 해당 테이블만 검색."""
        if item_type in ("item", None) and name in self.id_table.items:
            return self.id_table.items[name]
        if item_type in ("weapon", None) and name in self.id_table.weapons:
            return self.id_table.weapons[name]
        if item_type in ("armor", None) and name in self.id_table.armors:
            return self.id_table.armors[name]
        raise CompileError(f"아이템 '{name}' (type={item_type})을 id_table에서 찾을 수 없음")

    def resolve_troop_id(self, name: str) -> int:
        if name not in self.id_table.troops:
            raise CompileError(f"트루프 '{name}'을 id_table에서 찾을 수 없음")
        return self.id_table.troops[name]

    def resolve_switch_id(self, name: str) -> int:
        """스위치 이름 → ID. 없으면 새로 할당 (SwitchTable 불변, model_copy 패턴).

        이름은 SwitchTable.allocate_switch에서 정규화됨 (공백→밑줄).
        """
        from agent.generation.registry.switch_table import normalize_switch_name

        name = normalize_switch_name(name)
        if name not in self.switch_table.switches:
            self.switch_table, _ = self.switch_table.allocate_switch(name)
        return self.switch_table.switches[name]

    # ── 진입점 ───────────────────────────────────────────────────────────────

    def compile(self, dsl_event: DslEvent) -> dict:  # type: ignore[valid-type]
        """DslEvent → RPG Maker MZ 이벤트 dict."""
        match dsl_event.type:
            case "npc":
                return self._compile_npc(dsl_event)  # type: ignore[arg-type]
            case "transfer":
                return self._compile_transfer(dsl_event)  # type: ignore[arg-type]
            case "chest":
                return self._compile_chest(dsl_event)  # type: ignore[arg-type]
            case "battle":
                return self._compile_battle(dsl_event)  # type: ignore[arg-type]
            case "shop":
                return self._compile_shop(dsl_event)  # type: ignore[arg-type]
            case "ending":
                return self._compile_ending(dsl_event)  # type: ignore[arg-type]
            case _:
                raise CompileError(f"미지원 DSL 타입: {dsl_event.type}")

    # ── NPC ──────────────────────────────────────────────────────────────────

    def _compile_npc(self, event: NpcEvent) -> dict:
        """NpcEvent → 1~3페이지 이벤트.

        페이지 1: 기본 대화 (조건 없음). set_switch, give_item 처리.
        페이지 2 (hint_switch+hint_dialogue): 힌트 대화. 조건: hint_switch ON.
        페이지 2/3 (condition_switch+alt_dialogue): 보상/조건부 대화.
                  consume_item, unlock_switch 처리. 조건: condition_switch ON 또는 required_item.

        hint_switch + condition_switch 둘 다 있으면 3페이지.
        hint_switch만 있으면 2페이지 (기본+힌트).
        condition_switch/required_item만 있으면 2페이지 (기존 동작 유지).
        """
        if event.condition_switch and not event.alt_dialogue:
            logger.warning("NpcEvent '%s': condition_switch 있지만 alt_dialogue 없음", event.name)

        pages = []

        # ── 페이지 1: 기본 대화 (조건 없음) ──
        page1_cmds = _build_dialogue_commands(
            event.face_image, event.face_index, event.name, event.dialogue
        )
        if event.set_switch:
            sw_id = self.resolve_switch_id(event.set_switch)
            page1_cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})
        if event.give_item:
            give_item_id = self.resolve_item_id(event.give_item)
            page1_cmds.append({"code": 126, "indent": 0, "parameters": [give_item_id, 0, 0, 1]})
        page1_cmds.append({"code": 0, "indent": 0, "parameters": []})
        pages.append(
            _make_page(
                page1_cmds,
                _empty_conditions(),
                _trigger_code(event.trigger),
                character_name=event.character_name,
                character_index=event.character_index,
            )
        )

        # ── 페이지 2 (힌트): hint_switch + hint_dialogue ──
        if event.hint_switch and event.hint_dialogue:
            hint_sw_id = self.resolve_switch_id(event.hint_switch)
            hint_cmds = _build_dialogue_commands(
                event.face_image, event.face_index, event.name, event.hint_dialogue
            )
            hint_cmds.append({"code": 0, "indent": 0, "parameters": []})
            pages.append(
                _make_page(
                    hint_cmds,
                    _make_switch_condition(hint_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            )

        # ── 보상/조건부 페이지: condition_switch 또는 required_item ──
        if event.condition_switch and event.alt_dialogue:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)
            reward_cmds: list[dict] = []
            if event.consume_item and event.required_item:
                consume_item_id = self.resolve_item_id(event.required_item)
                reward_cmds.append(
                    {"code": 126, "indent": 0, "parameters": [consume_item_id, 0, 1, 1]}
                )
            reward_cmds.extend(
                _build_dialogue_commands(
                    event.face_image, event.face_index, event.name, event.alt_dialogue
                )
            )
            if event.unlock_switch:
                unlock_sw_id = self.resolve_switch_id(event.unlock_switch)
                reward_cmds.append(
                    {"code": 121, "indent": 0, "parameters": [unlock_sw_id, unlock_sw_id, 0]}
                )
            reward_cmds.append({"code": 0, "indent": 0, "parameters": []})
            pages.append(
                _make_page(
                    reward_cmds,
                    _make_switch_condition(cond_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            )
        elif event.required_item and event.alt_dialogue:
            item_id = self.resolve_item_id(event.required_item)
            item_cmds: list[dict] = []
            if event.consume_item:
                item_cmds.append({"code": 126, "indent": 0, "parameters": [item_id, 0, 1, 1]})
            item_cmds.extend(
                _build_dialogue_commands(
                    event.face_image, event.face_index, event.name, event.alt_dialogue
                )
            )
            if event.unlock_switch:
                unlock_sw_id = self.resolve_switch_id(event.unlock_switch)
                item_cmds.append(
                    {"code": 121, "indent": 0, "parameters": [unlock_sw_id, unlock_sw_id, 0]}
                )
            item_cmds.append({"code": 0, "indent": 0, "parameters": []})
            pages.append(
                _make_page(
                    item_cmds,
                    _make_item_condition(item_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            )

        return _make_event(event.name, event.x, event.y, pages)

    # ── Transfer ─────────────────────────────────────────────────────────────

    def _compile_transfer(self, event: TransferEvent) -> dict:
        map_id = self.resolve_map_id(event.to_map)
        direction = _DIRECTION_CODE.get(event.direction, 0)

        transfer_cmds: list[dict] = []
        transfer_cmds.append(
            {
                "code": 201,
                "indent": 0,
                "parameters": [0, map_id, event.to_x, event.to_y, direction, 0],
            }
        )
        if event.set_switch:
            sw_id = self.resolve_switch_id(event.set_switch)
            transfer_cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})
        transfer_cmds.append({"code": 0, "indent": 0, "parameters": []})

        if event.condition_switch:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)

            # page1: 조건 없음 — 차단 메시지 (switch OFF 시 활성)
            page1_cmds: list[dict] = []
            if event.blocked_dialogue:
                page1_cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]})
                page1_cmds.append(
                    {"code": 401, "indent": 0, "parameters": [event.blocked_dialogue]}
                )
            page1_cmds.append({"code": 0, "indent": 0, "parameters": []})

            # page2: switch ON → 이동 실행
            pages = [
                _make_page(
                    page1_cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
                _make_page(
                    transfer_cmds,
                    _make_switch_condition(cond_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
            ]
        else:
            pages = [
                _make_page(
                    transfer_cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            ]

        return _make_event(event.name, event.x, event.y, pages)

    # ── Chest ────────────────────────────────────────────────────────────────

    def _compile_chest(self, event: ChestEvent) -> dict:
        item_id = self.resolve_item_id(event.item, event.item_type)
        cmds: list[dict] = []

        # one_time 블록은 111(If)로 감싸고, 내부 커맨드는 indent 1
        # parameters[2]=1 → "스위치가 OFF일 때" 실행 (아직 열지 않은 경우에만 동작)
        indent = 0
        if event.one_time and event.chest_switch:
            sw_id = self.resolve_switch_id(event.chest_switch)
            cmds.append({"code": 111, "indent": 0, "parameters": [0, sw_id, 1]})
            indent = 1

        if event.dialogue_before:
            cmds.append({"code": 101, "indent": indent, "parameters": ["", 0, 0, 2, ""]})
            cmds.append({"code": 401, "indent": indent, "parameters": [event.dialogue_before]})

        # 아이템 획득 커맨드
        item_code = _item_change_code(event.item_type)
        if item_code == 126:
            cmds.append(
                {"code": 126, "indent": indent, "parameters": [item_id, 0, 0, event.amount]}
            )
        elif item_code == 127:
            cmds.append(
                {"code": 127, "indent": indent, "parameters": [item_id, 0, 0, event.amount, False]}
            )
        elif item_code == 128:
            cmds.append(
                {"code": 128, "indent": indent, "parameters": [item_id, 0, 0, event.amount, False]}
            )

        if event.dialogue_after:
            # 401 단독 사용 불가 — 반드시 101 헤더 선행
            cmds.append({"code": 101, "indent": indent, "parameters": ["", 0, 0, 2, ""]})
            cmds.append({"code": 401, "indent": indent, "parameters": [event.dialogue_after]})

        if event.one_time and event.chest_switch:
            sw_id = self.switch_table.switches[event.chest_switch]
            cmds.append({"code": 121, "indent": indent, "parameters": [sw_id, sw_id, 0]})
            cmds.append({"code": 412, "indent": 0, "parameters": []})  # End If

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        if event.condition_switch:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)
            page1 = _make_page(
                [{"code": 0, "indent": 0, "parameters": []}],
                _empty_conditions(),
                _trigger_code("action_button"),
                character_name="",  # 숨겨진 상태
                character_index=0,
            )
            page2 = _make_page(
                cmds,
                _make_switch_condition(cond_sw_id),
                _trigger_code("action_button"),
                character_name=event.character_name,
                character_index=event.character_index,
            )
            return _make_event(event.name, event.x, event.y, [page1, page2])

        page = _make_page(
            cmds,
            _empty_conditions(),
            _trigger_code("action_button"),
            character_name=event.character_name,
            character_index=event.character_index,
        )
        return _make_event(event.name, event.x, event.y, [page])

    # ── Battle ───────────────────────────────────────────────────────────────

    def _compile_battle(self, event: BattleEvent) -> dict:
        troop_id = self.resolve_troop_id(event.troop)
        can_lose = event.lose_condition != "game_over"
        cmds: list[dict] = []

        # one_time 블록은 111(If)로 감싸고, 내부 커맨드는 indent+1
        # parameters[2]=1 → "스위치가 OFF일 때" 실행 (아직 처치하지 않은 경우에만 전투 발생)
        base_indent = 0
        if event.one_time and event.battle_switch:
            sw_id = self.resolve_switch_id(event.battle_switch)
            cmds.append({"code": 111, "indent": 0, "parameters": [0, sw_id, 1]})
            base_indent = 1

        cmds.append(
            {
                "code": 301,
                "indent": base_indent,
                "parameters": [0, troop_id, event.escape_allowed, can_lose],
            }
        )

        # If Win (601) — 내부 커맨드는 base_indent+1
        cmds.append({"code": 601, "indent": base_indent, "parameters": []})
        for action in event.on_win:
            if action.give_item:
                item_name = action.give_item.get("item", "")
                amount = action.give_item.get("amount", 1)
                try:
                    iid = self.resolve_item_id(item_name)
                    cmds.append(
                        {"code": 126, "indent": base_indent + 1, "parameters": [iid, 0, 0, amount]}
                    )
                except CompileError:
                    logger.warning("battle on_win: 아이템 '%s' 찾을 수 없음, 건너뜀", item_name)
            if action.set_switch:
                sw_id = self.resolve_switch_id(action.set_switch)
                cmds.append(
                    {"code": 121, "indent": base_indent + 1, "parameters": [sw_id, sw_id, 0]}
                )

        if event.one_time and event.battle_switch:
            sw_id = self.switch_table.switches[event.battle_switch]
            cmds.append({"code": 121, "indent": base_indent + 1, "parameters": [sw_id, sw_id, 0]})

        # If Escape (602)
        cmds.append({"code": 602, "indent": base_indent, "parameters": []})
        # If Lose (603) → game_over or continue
        cmds.append({"code": 603, "indent": base_indent, "parameters": []})
        if event.lose_condition == "game_over":
            cmds.append({"code": 353, "indent": base_indent + 1, "parameters": []})

        # End Battle Processing: 604 (412는 조건분기 종료, 전투처리 종료는 604)
        cmds.append({"code": 604, "indent": base_indent, "parameters": []})

        if event.one_time and event.battle_switch:
            cmds.append({"code": 412, "indent": 0, "parameters": []})  # End If

        cmds.append({"code": 0, "indent": 0, "parameters": []})
        # through=False(기본) + priorityType=1 → 이동 차단
        # 차단 시 checkEventTriggerThere([0]) 발동 → action_button(0) 이벤트 자동 실행
        # 플레이어가 몬스터 방향으로 이동 시도하면 막히면서 전투 발동 (player_touch와 동일 체감)
        page = _make_page(
            cmds,
            _empty_conditions(),
            trigger=0,  # action_button: 막힐 때 자동 발동
            character_name=event.character_name,
            character_index=event.character_index,
        )
        return _make_event(event.name, event.x, event.y, [page])

    # ── Shop ─────────────────────────────────────────────────────────────────

    def _compile_shop(self, event: ShopEvent) -> dict:
        if not event.items:
            raise CompileError(f"상점 '{event.name}'에 상품이 없음")

        cmds: list[dict] = []

        if event.dialogue:
            cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, event.name]})
            cmds.append({"code": 401, "indent": 0, "parameters": [event.dialogue]})

        first = event.items[0]
        goods_type = _ITEM_TYPE_TO_GOODS_CODE.get(first.item_type, 0)
        goods_id = self.resolve_item_id(first.item, first.item_type)
        purchase_flag = 1 if event.purchase_only else 0
        cmds.append(
            {
                "code": 302,
                "indent": 0,
                "parameters": [goods_type, goods_id, 0, 0, purchase_flag, False],
            }
        )

        for item_spec in event.items[1:]:
            gtype = _ITEM_TYPE_TO_GOODS_CODE.get(item_spec.item_type, 0)
            gid = self.resolve_item_id(item_spec.item, item_spec.item_type)
            cmds.append({"code": 605, "indent": 0, "parameters": [gtype, gid, 0, 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        if event.condition_switch:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)

            page1_cmds = [{"code": 0, "indent": 0, "parameters": []}]
            pages = [
                _make_page(
                    page1_cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
                _make_page(
                    cmds,
                    _make_switch_condition(cond_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                ),
            ]
        else:
            pages = [
                _make_page(
                    cmds,
                    _empty_conditions(),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                )
            ]

        return _make_event(event.name, event.x, event.y, pages)

    # ── Ending ───────────────────────────────────────────────────────────────

    def _compile_ending(self, event: EndingEvent) -> dict:
        cond_sw_id = self.resolve_switch_id(event.condition_switch)

        # 페이지 1: condition_switch=ON 시 Auto-Run 엔딩 실행
        cmds: list[dict] = []
        cmds.append({"code": 230, "indent": 0, "parameters": [60]})  # Wait 1초

        for line in event.lines:
            cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, ""]})
            cmds.append({"code": 401, "indent": 0, "parameters": [line]})

        cmds.append({"code": 230, "indent": 0, "parameters": [60]})
        cmds.append({"code": 221, "indent": 0, "parameters": []})  # Fadeout
        cmds.append({"code": 230, "indent": 0, "parameters": [60]})

        if event.action == "title":
            cmds.append({"code": 354, "indent": 0, "parameters": []})  # Return to Title
        else:
            cmds.append({"code": 353, "indent": 0, "parameters": []})  # Game Over

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        # RPG Maker MZ는 마지막 유효 페이지를 사용 — switch 조건 페이지가 반드시 마지막
        # 페이지1: 조건 없음, 아무것도 안 함 (switch OFF 시 대기)
        # 페이지2: condition_switch=ON → Auto-Run 엔딩 실행
        page1_cmds = [{"code": 0, "indent": 0, "parameters": []}]

        pages = [
            _make_page(
                page1_cmds, _empty_conditions(), trigger=0
            ),  # Page 1: Action Button — switch OFF 시 대기 (autorun 금지, 소프트락 방지)
            _make_page(
                cmds, _make_switch_condition(cond_sw_id), trigger=3
            ),  # Page 2: switch ON 시 Auto-Run 엔딩
        ]
        return _make_event(event.name, event.x, event.y, pages)


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────


def _trigger_code(trigger: str) -> int:
    return _TRIGGER_CODE.get(trigger, 0)


def _item_change_code(item_type: str) -> int:
    """item_type → Change 커맨드 코드."""
    return {"item": 126, "weapon": 127, "armor": 128}.get(item_type, 126)


def _wrap_text(text: str, max_chars: int = 22) -> list[str]:
    """RPG Maker MZ 메시지창 너비에 맞게 텍스트 자동 줄바꿈.

    한국어 22자/줄 기준 (screenWidth=816, faceSize=144, fontSize=26).
    분할 순서:
      1. 마침표·느낌표·물음표 기준 → 자연스러운 문장 단위 분할
      2. 여전히 초과 시 공백 기준 분할
      3. 공백 없고 초과 시 글자 수 강제 분할
    """
    import re

    if len(text) <= max_chars:
        return [text]

    result: list[str] = []

    # 1단계: 문장 끝 구두점 기준 분할 (구두점은 앞 문장에 포함)
    sentences = [s.strip() for s in re.split(r"(?<=[.。!?！？])\s*", text) if s.strip()]
    if not sentences:
        sentences = [text]

    for sentence in sentences:
        if len(sentence) <= max_chars:
            result.append(sentence)
            continue

        # 2단계: 공백 기준 분할
        words = sentence.split(" ")
        current = ""
        for word in words:
            if not current:
                current = word
            elif len(current) + 1 + len(word) <= max_chars:
                current += " " + word
            else:
                if current:
                    result.append(current)
                current = word

        # 3단계: 남은 current가 초과면 글자 수 강제 분할
        while len(current) > max_chars:
            result.append(current[:max_chars])
            current = current[max_chars:]
        if current:
            result.append(current)

    return [r for r in result if r] or [text]


def _build_dialogue_commands(
    face_image: str, face_index: int, speaker: str, lines: list[str]
) -> list[dict]:
    """ShowText 커맨드 시퀀스 (101 + 401×N, 4줄마다 새 101).

    각 라인을 _wrap_text로 분할하여 메시지창 너비 초과를 방지.
    """
    # 각 라인을 래핑 후 평탄화 (최대 22자/줄)
    wrapped: list[str] = []
    for line in lines:
        wrapped.extend(_wrap_text(line))

    cmds: list[dict] = []
    for chunk_start in range(0, len(wrapped), 4):
        chunk = wrapped[chunk_start : chunk_start + 4]
        cmds.append(
            {
                "code": 101,
                "indent": 0,
                "parameters": [face_image, face_index, 0, 2, speaker],
            }
        )
        for line in chunk:
            cmds.append({"code": 401, "indent": 0, "parameters": [line]})
    return cmds


def _make_item_condition(item_id: int) -> dict:
    cond = _empty_conditions()
    cond["itemId"] = item_id
    cond["itemValid"] = True
    return cond


def _make_switch_condition(switch_id: int) -> dict:
    return {
        "actorId": 1,
        "actorValid": False,
        "itemId": 1,
        "itemValid": False,
        "selfSwitchCh": "A",
        "selfSwitchValid": False,
        "switch1Id": switch_id,
        "switch1Valid": True,
        "switch2Id": 1,
        "switch2Valid": False,
        "variableId": 1,
        "variableValid": False,
        "variableValue": 0,
    }


def _empty_conditions() -> dict:
    return {
        "actorId": 1,
        "actorValid": False,
        "itemId": 1,
        "itemValid": False,
        "selfSwitchCh": "A",
        "selfSwitchValid": False,
        "switch1Id": 1,
        "switch1Valid": False,
        "switch2Id": 1,
        "switch2Valid": False,
        "variableId": 1,
        "variableValid": False,
        "variableValue": 0,
    }


def _make_page(
    cmds: list[dict],
    conditions: dict,
    trigger: int,
    direction_fix: bool = True,
    priority: int = 1,
    walk_anime: bool = True,
    step_anime: bool = False,
    character_name: str = "",
    character_index: int = 0,
    through: bool = False,
) -> dict:
    return {
        "conditions": conditions,
        "directionFix": direction_fix,
        "image": {
            "characterIndex": character_index,
            "characterName": character_name,
            "direction": 2,
            "pattern": 0,
            "tileId": 0,
        },
        "list": cmds,
        "moveFrequency": 3,
        "moveRoute": {
            "list": [{"code": 0, "parameters": []}],
            "repeat": True,
            "skippable": False,
            "wait": False,
        },
        "moveSpeed": 3,
        "moveType": 0,
        "priorityType": priority,
        "stepAnime": step_anime,
        "through": through,
        "trigger": trigger,
        "walkAnime": walk_anime,
    }


def _make_event(name: str, x: int, y: int, pages: list[dict]) -> dict:
    return {
        "id": 0,  # integrator가 최종 ID 할당
        "name": name,
        "note": "",
        "pages": pages,
        "x": x,
        "y": y,
    }
