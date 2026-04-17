"""EventCompiler — DSL → RPG Maker MZ 커맨드 변환.

canonical: docs/The_world/dsl_specification.md §컴파일러 구현 상세
canonical: docs/The_world/npc_conditional_and_shop.md
canonical: docs/The_world/game_ending_design.md
"""

import logging
import random
import re

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    ChestEvent,
    DslEvent,
    EndingEvent,
    GateEvent,
    NpcEvent,
    QuestChestEvent,
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

# 보물상자 애니메이션 ID (RPG Maker MZ 기본 에셋)
_CHEST_OPEN_ANIMATION_ID = 48  # 상자 열릴 때
_CHEST_CLOSE_ANIMATION_ID = 52  # 상자 사라질 때

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

    @staticmethod
    def _normalize_name(name: str) -> str:
        """이름 정규화: 공백·특수문자 제거, 소문자 변환.

        LLM이 생성한 이름과 id_table 등록 이름의 미묘한 차이
        (공백 유무, 대소문자, 괄호 등)를 허용한다.
        예: "수변 상업 지구" → "수변상업지구", "SF Actor1" → "sfactor1"
        """
        return re.sub(r"[\s\-_·()（）]", "", name).lower()

    def resolve_map_id(self, name: str) -> int:
        # 1차: 정확히 일치
        if name in self.id_table.maps:
            return self.id_table.maps[name]
        # 2차: 공백·특수문자 정규화 후 비교
        normalized = self._normalize_name(name)
        for k, v in self.id_table.maps.items():
            if self._normalize_name(k) == normalized:
                logger.info("resolve_map_id: '%s' → '%s' 정규화 매칭", name, k)
                return v
        raise CompileError(f"맵 '{name}'을 id_table에서 찾을 수 없음")

    def resolve_item_id(self, name: str, item_type: str | None = None) -> int:
        """아이템 이름 → ID. item_type 지정 시 해당 테이블만 검색."""
        # 1차: 정확히 일치
        if item_type in ("item", None) and name in self.id_table.items:
            return self.id_table.items[name]
        if item_type in ("weapon", None) and name in self.id_table.weapons:
            return self.id_table.weapons[name]
        if item_type in ("armor", None) and name in self.id_table.armors:
            return self.id_table.armors[name]
        # 2차: 공백·특수문자 정규화 후 비교
        normalized = self._normalize_name(name)
        tables = []
        if item_type in ("item", None):
            tables.append(self.id_table.items)
        if item_type in ("weapon", None):
            tables.append(self.id_table.weapons)
        if item_type in ("armor", None):
            tables.append(self.id_table.armors)
        for table in tables:
            for k, v in table.items():
                if self._normalize_name(k) == normalized:
                    logger.info("resolve_item_id: '%s' → '%s' 정규화 매칭", name, k)
                    return v
        raise CompileError(f"아이템 '{name}' (type={item_type})을 id_table에서 찾을 수 없음")

    def resolve_troop_id(self, name: str) -> int:
        if name in self.id_table.troops:
            return self.id_table.troops[name]
        # 정규화: 공백→밑줄, × 통일
        from agent.generation.registry.switch_table import normalize_switch_name

        normalized = normalize_switch_name(name).replace("x", "×")
        for troop_name, tid in self.id_table.troops.items():
            if normalize_switch_name(troop_name).replace("x", "×") == normalized:
                return tid
        # 부분 매칭: 적 이름이 포함된 troop
        base_name = name.split("×")[0].split("_")[0].strip()
        for troop_name, tid in self.id_table.troops.items():
            if base_name in troop_name:
                logger.warning("troop '%s' → '%s' 퍼지 매칭", name, troop_name)
                return tid
        raise CompileError(f"트루프 '{name}'을 id_table에서 찾을 수 없음")

    def resolve_switch_id(self, name: str) -> int:
        """스위치 이름 → ID. 없으면 새로 할당 (SwitchTable 불변, model_copy 패턴)."""
        self.switch_table, sw_id = self.switch_table.allocate_switch(name)
        return sw_id

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
            case "gate":
                return self._compile_gate(dsl_event)  # type: ignore[arg-type]
            case "quest_chest":
                return self._compile_quest_chest(dsl_event)  # type: ignore[arg-type]
            case _:
                raise CompileError(f"미지원 DSL 타입: {dsl_event.type}")

    # ── NPC ──────────────────────────────────────────────────────────────────

    def _compile_npc(self, event: NpcEvent) -> dict:
        """NpcEvent → 1~2페이지 이벤트.

        페이지 1: 기본 대화 (조건 없음)
        페이지 2: alt_dialogue 있을 때만, condition_switch=ON 조건
        """
        if event.condition_switch and not event.alt_dialogue:
            logger.warning("NpcEvent '%s': condition_switch 있지만 alt_dialogue 없음", event.name)

        pages = []

        # 페이지 1: 기본 대화
        page1_cmds = _build_dialogue_commands(
            event.face_image, event.face_index, event.name, event.dialogue
        )
        if event.set_switch:
            sw_id = self.resolve_switch_id(event.set_switch)
            page1_cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})
        page1_cmds.append({"code": 0, "indent": 0, "parameters": []})
        pages.append(
            _make_page(
                page1_cmds,
                _empty_conditions(),
                _trigger_code(event.trigger),
                character_name=event.character_name,
                character_index=event.character_index,
                move_type=1,
                move_speed=random.randint(2, 4),
                move_frequency=4,
            )
        )

        # 페이지 2: 조건부 대화
        if event.condition_switch and event.alt_dialogue:
            cond_sw_id = self.resolve_switch_id(event.condition_switch)
            page2_cmds = _build_dialogue_commands(
                event.face_image, event.face_index, event.name, event.alt_dialogue
            )
            page2_cmds.append({"code": 0, "indent": 0, "parameters": []})
            pages.append(
                _make_page(
                    page2_cmds,
                    _make_switch_condition(cond_sw_id),
                    _trigger_code(event.trigger),
                    character_name=event.character_name,
                    character_index=event.character_index,
                    move_type=1,
                    move_speed=random.randint(2, 4),
                    move_frequency=4,
                )
            )

        return _make_event(event.name, event.x, event.y, pages)

    # ── Transfer ─────────────────────────────────────────────────────────────

    def _compile_transfer(self, event: TransferEvent) -> dict:
        map_id = self.resolve_map_id(event.to_map)
        direction = _DIRECTION_CODE.get(event.direction, 0)
        trigger = _trigger_code(event.trigger)

        # 이동 커맨드 (조건부/비조건부 공통)
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
            # 조건부 워프: 2페이지 구성
            # 페이지 1 (조건 OFF): blocked_message 출력 또는 빈 이벤트
            cond_sw_id = self.resolve_switch_id(event.condition_switch)
            if event.blocked_message:
                blocked_cmds = _build_dialogue_commands("", 0, "", [event.blocked_message])
                blocked_cmds.append({"code": 0, "indent": 0, "parameters": []})
            else:
                blocked_cmds = [{"code": 0, "indent": 0, "parameters": []}]

            page1 = _make_page(
                blocked_cmds,
                _empty_conditions(),
                trigger,
                character_name=event.character_name,
                character_index=event.character_index,
                direction_fix=True,
            )
            # 페이지 2 (조건 ON): 실제 이동
            page2 = _make_page(
                transfer_cmds,
                _make_switch_condition(cond_sw_id),
                trigger,
                character_name=event.character_name,
                character_index=event.character_index,
                direction_fix=True,
            )
            return _make_event(event.name, event.x, event.y, [page1, page2])

        page = _make_page(
            transfer_cmds,
            _empty_conditions(),
            trigger,
            character_name=event.character_name,
            character_index=event.character_index,
            direction_fix=True,
        )
        return _make_event(event.name, event.x, event.y, [page])

    # ── Chest ────────────────────────────────────────────────────────────────

    def _compile_chest(self, event: ChestEvent) -> dict:
        item_id = self.resolve_item_id(event.item, event.item_type)
        chest_cmds = self._build_chest_commands(event, item_id)

        # 획득 후 상자 사라짐 페이지 (chest_switch ON 시 투명 빈 페이지)
        disappeared_page = None
        if event.one_time and event.chest_switch:
            chest_sw_id = self.resolve_switch_id(event.chest_switch)
            disappeared_page = _make_page(
                [{"code": 0, "indent": 0, "parameters": []}],
                _make_switch_condition(chest_sw_id),
                trigger=0,
                character_name="",
                character_index=0,
                through=True,
                priority=0,
            )

        if event.condition_switch:
            # 조건부 chest: 2페이지 구성 (+ 소멸 페이지)
            # 페이지 1 (조건 OFF): 투명 빈 페이지 — chest가 보이지 않음
            # 페이지 2 (조건 ON): chest 등장 및 아이템 획득
            # 페이지 3 (chest_switch ON): 획득 후 완전 소멸
            cond_sw_id = self.resolve_switch_id(event.condition_switch)
            page1 = _make_page(
                [{"code": 0, "indent": 0, "parameters": []}],
                _empty_conditions(),
                trigger=0,
                character_name="",  # 투명 스프라이트
                character_index=0,
                through=True,
                priority=0,
            )
            page2 = _make_page(
                chest_cmds,
                _make_switch_condition(cond_sw_id),
                trigger=0,  # action_button
                character_name=event.character_name,
                character_index=event.character_index,
                direction_fix=True,
            )
            pages = [page1, page2]
            if disappeared_page:
                pages.append(disappeared_page)
            return _make_event(event.name, event.x, event.y, pages)

        page = _make_page(
            chest_cmds,
            _empty_conditions(),
            _trigger_code("action_button"),
            character_name=event.character_name,
            character_index=event.character_index,
            direction_fix=True,
        )
        pages = [page]
        if disappeared_page:
            pages.append(disappeared_page)
        return _make_event(event.name, event.x, event.y, pages)

    def _build_chest_commands(self, event: ChestEvent, item_id: int) -> list[dict]:
        """chest 아이템 획득 커맨드 시퀀스 생성 (조건부/비조건부 공통)."""
        cmds: list[dict] = []

        # one_time 블록은 111(If)로 감싸고, 내부 커맨드는 indent 1
        # parameters[2]=1 → "스위치가 OFF일 때" 실행 (아직 열지 않은 경우에만 동작)
        indent = 0
        if event.one_time and event.chest_switch:
            sw_id = self.resolve_switch_id(event.chest_switch)
            cmds.append({"code": 111, "indent": 0, "parameters": [0, sw_id, 1]})
            indent = 1
            # 상자 열림 애니메이션 (wait=True: 애니메이션 완료 후 대화 시작)
            cmds.append(
                {"code": 212, "indent": indent, "parameters": [-1, _CHEST_OPEN_ANIMATION_ID, True]}
            )

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
            # 상자 사라짐 애니메이션 (wait=False: 스위치 ON과 동시에 재생)
            cmds.append(
                {
                    "code": 212,
                    "indent": indent,
                    "parameters": [-1, _CHEST_CLOSE_ANIMATION_ID, False],
                }
            )
            cmds.append({"code": 121, "indent": indent, "parameters": [sw_id, sw_id, 0]})
            cmds.append({"code": 412, "indent": 0, "parameters": []})  # End If

        cmds.append({"code": 0, "indent": 0, "parameters": []})
        return cmds

    def _build_quest_chest_commands(
        self,
        item_id: int,
        item_type: str,
        amount: int,
        chest_switch: str,
        dialogue_before: str = "",
        dialogue_after: str = "",
    ) -> list[dict]:
        """QuestChestEvent 보물상자 페이지용 커맨드 (one_time 고정)."""
        cmds: list[dict] = []
        sw_id = self.resolve_switch_id(chest_switch)

        # one_time: chest_switch OFF일 때만 실행
        cmds.append({"code": 111, "indent": 0, "parameters": [0, sw_id, 1]})
        indent = 1
        # 상자 열림 애니메이션 (wait=True: 애니메이션 완료 후 대화 시작)
        cmds.append(
            {"code": 212, "indent": indent, "parameters": [-1, _CHEST_OPEN_ANIMATION_ID, True]}
        )

        if dialogue_before:
            cmds.append({"code": 101, "indent": indent, "parameters": ["", 0, 0, 2, ""]})
            cmds.append({"code": 401, "indent": indent, "parameters": [dialogue_before]})

        item_code = _item_change_code(item_type)
        if item_code == 126:
            cmds.append({"code": 126, "indent": indent, "parameters": [item_id, 0, 0, amount]})
        elif item_code == 127:
            cmds.append(
                {"code": 127, "indent": indent, "parameters": [item_id, 0, 0, amount, False]}
            )
        elif item_code == 128:
            cmds.append(
                {"code": 128, "indent": indent, "parameters": [item_id, 0, 0, amount, False]}
            )

        if dialogue_after:
            cmds.append({"code": 101, "indent": indent, "parameters": ["", 0, 0, 2, ""]})
            cmds.append({"code": 401, "indent": indent, "parameters": [dialogue_after]})

        # 상자 사라짐 애니메이션 (wait=False: 스위치 ON과 동시에 재생)
        cmds.append(
            {"code": 212, "indent": indent, "parameters": [-1, _CHEST_CLOSE_ANIMATION_ID, False]}
        )
        cmds.append({"code": 121, "indent": indent, "parameters": [sw_id, sw_id, 0]})
        cmds.append({"code": 412, "indent": 0, "parameters": []})  # End If
        cmds.append({"code": 0, "indent": 0, "parameters": []})
        return cmds

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
            # on_win에서 이미 ON한 스위치와 중복이면 생략
            on_win_switches = {a.set_switch for a in event.on_win if a.set_switch}
            if event.battle_switch not in on_win_switches:
                sw_id = self.resolve_switch_id(event.battle_switch)
                cmds.append(
                    {"code": 121, "indent": base_indent + 1, "parameters": [sw_id, sw_id, 0]}
                )

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
            move_type=1,
            move_speed=random.randint(3, 5),
            move_frequency=5,
        )

        if event.one_time and event.battle_switch:
            battle_sw_id = self.resolve_switch_id(event.battle_switch)
            disappeared_page = _make_page(
                [{"code": 0, "indent": 0, "parameters": []}],
                _make_switch_condition(battle_sw_id),
                trigger=0,
                character_name="",
                character_index=0,
                through=True,
                priority=0,
            )
            return _make_event(event.name, event.x, event.y, [page, disappeared_page])

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
        cmds.append(
            {
                "code": 302,
                "indent": 0,
                "parameters": [goods_type, goods_id, 0, 0, bool(event.purchase_only)],
            }
        )

        for item_spec in event.items[1:]:
            gtype = _ITEM_TYPE_TO_GOODS_CODE.get(item_spec.item_type, 0)
            gid = self.resolve_item_id(item_spec.item, item_spec.item_type)
            cmds.append({"code": 605, "indent": 0, "parameters": [gtype, gid, 0, 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})
        page = _make_page(
            cmds,
            _empty_conditions(),
            _trigger_code(event.trigger),
            character_name=event.character_name,
            character_index=event.character_index,
            move_type=1,
            move_speed=random.randint(2, 4),
            move_frequency=4,
        )
        return _make_event(event.name, event.x, event.y, [page])

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

    # ── Gate ─────────────────────────────────────────────────────────────────

    def _compile_gate(self, event: GateEvent) -> dict:
        """NPC 문지기 → 워프 전환 이벤트 컴파일.

        페이지 구성:
          Page 1 (조건 없음):          NPC 스프라이트 + stage_dialogues[0]
          Page 2 (switch1 ON):         NPC 스프라이트 + stage_dialogues[1]  (2개 조건인 경우)
          Page N (모든 조건 ON):       워프 스프라이트 + player_touch → 이동
        """
        map_id = self.resolve_map_id(event.to_map)
        direction = _DIRECTION_CODE.get(event.direction, 0)
        cond_sw_ids = [self.resolve_switch_id(sw) for sw in event.condition_switches]

        # stage_dialogues 정규화:
        # - condition_switches 수와 일치하도록 자르거나 기본 대사로 패딩
        # - 빈 문자열은 기본 대사로 교체 (빈 대화창 방지)
        _fallback_hint = "아직 조건이 충족되지 않았습니다."
        dialogues: list[str] = [
            d.strip() or _fallback_hint for d in event.stage_dialogues[: len(cond_sw_ids)]
        ]
        while len(dialogues) < len(cond_sw_ids):
            dialogues.append(_fallback_hint)

        pages: list[dict] = []

        # 힌트 페이지: 조건이 하나씩 충족될수록 다음 페이지로 전환
        for i, dialogue in enumerate(dialogues):
            conditions = _empty_conditions()
            if i >= 1:
                conditions["switch1Id"] = cond_sw_ids[0]
                conditions["switch1Valid"] = True
            if i >= 2 and len(cond_sw_ids) >= 2:
                conditions["switch2Id"] = cond_sw_ids[1]
                conditions["switch2Valid"] = True

            cmds = _build_dialogue_commands("", 0, event.name, [dialogue])
            cmds.append({"code": 0, "indent": 0, "parameters": []})

            pages.append(
                _make_page(
                    cmds,
                    conditions,
                    trigger=0,  # action_button
                    character_name=event.keeper_character_name,
                    character_index=event.keeper_character_index,
                    move_type=1,
                    move_speed=random.randint(2, 4),
                    move_frequency=4,
                )
            )

        # 최종 워프 페이지: 모든 조건 충족 시
        final_conditions = _empty_conditions()
        if len(cond_sw_ids) >= 1:
            final_conditions["switch1Id"] = cond_sw_ids[0]
            final_conditions["switch1Valid"] = True
        if len(cond_sw_ids) >= 2:
            final_conditions["switch2Id"] = cond_sw_ids[1]
            final_conditions["switch2Valid"] = True

        transfer_cmds = [
            {
                "code": 201,
                "indent": 0,
                "parameters": [0, map_id, event.to_x, event.to_y, direction, 0],
            },
            {"code": 0, "indent": 0, "parameters": []},
        ]
        pages.append(
            _make_page(
                transfer_cmds,
                final_conditions,
                trigger=1,  # player_touch
                character_name=event.gate_character_name,
                character_index=event.gate_character_index,
                direction_fix=True,
            )
        )

        return _make_event(event.name, event.x, event.y, pages)

    # ── QuestChest ────────────────────────────────────────────────────────────

    def _compile_quest_chest(self, event: QuestChestEvent) -> dict:
        """퀘스트 완료 후 보물상자 전환 이벤트 컴파일.

        NPC 버전:
          Page 1 (quest_switch OFF): NPC 스프라이트 → 대화 → quest_switch ON
          Page 2 (quest_switch ON):  !Chest 스프라이트 → 아이템 획득
        몬스터 버전:
          Page 1 (quest_switch OFF): Monster 스프라이트 → 전투
                                     승리 시에만 quest_switch ON (도망/패배 시 유지)
          Page 2 (quest_switch ON):  !Chest 스프라이트 → 아이템 획득
        """
        quest_sw_id = self.resolve_switch_id(event.quest_switch)

        # ── Page 1: 퀘스트 진행 중 ───────────────────────────────────────────
        if event.quest_type == "npc":
            # Page 1: 힌트 대사만 출력 — quest_switch는 별도 NpcEvent가 ON시켜야 chest 등장
            # (여기서 스스로 ON하면 NPC 대화 즉시 chest로 변신 → 너무 쉬운 획득)
            npc_cmds = _build_dialogue_commands(
                "", 0, event.name, event.quest_dialogue or ["먼저 퀘스트를 받아야 합니다."]
            )
            npc_cmds.append({"code": 0, "indent": 0, "parameters": []})

            page1 = _make_page(
                npc_cmds,
                _empty_conditions(),
                trigger=0,  # action_button
                character_name=event.quest_character_name,
                character_index=event.quest_character_index,
                move_type=1,
            )
        else:  # battle
            if not event.troop:
                # troop 없으면 npc 타입으로 강제 폴백 (대화만 출력, quest_switch는 ON하지 않음)
                # ⚠️ quest_switch를 여기서 ON하면 전투 없이 상자 획득이 가능해지므로 절대 금지
                logger.warning(
                    "QuestChestEvent '%s': quest_type=battle이지만 troop 없음 → npc 힌트 전용 폴백 (quest_switch ON 없음)",
                    event.name,
                )
                npc_cmds = _build_dialogue_commands(
                    "",
                    0,
                    event.name,
                    event.quest_dialogue
                    or ["이 상자를 지키는 무언가가 있다.", "힘으로 제압해야 열릴 것 같다."],
                )
                npc_cmds.append({"code": 0, "indent": 0, "parameters": []})
                page1 = _make_page(
                    npc_cmds,
                    _empty_conditions(),
                    trigger=0,
                    character_name=event.quest_character_name,
                    character_index=event.quest_character_index,
                    move_type=1,
                    move_speed=random.randint(2, 4),
                )
                # Page 2: quest_switch ON 시 열리는 상자 (battle 이벤트가 quest_switch를 ON해야 함)
                item_id = self.resolve_item_id(event.item, event.item_type)
                chest_cmds = self._build_quest_chest_commands(
                    item_id=item_id,
                    item_type=event.item_type,
                    amount=event.amount,
                    chest_switch=event.chest_switch,
                    dialogue_before=event.dialogue_before,
                    dialogue_after=event.dialogue_after,
                )
                page2 = _make_page(
                    chest_cmds,
                    _make_switch_condition(quest_sw_id),
                    trigger=0,
                    character_name=event.chest_character_name,
                    character_index=event.chest_character_index,
                    direction_fix=True,
                )
                chest_sw_id = self.resolve_switch_id(event.chest_switch)
                page3 = _make_page(
                    [{"code": 0, "indent": 0, "parameters": []}],
                    _make_switch_condition(chest_sw_id),
                    trigger=0,
                    character_name="",
                    character_index=0,
                    through=True,
                    priority=0,
                )
                return _make_event(event.name, event.x, event.y, [page1, page2, page3])
            troop_id = self.resolve_troop_id(event.troop)
            can_lose = event.lose_condition != "game_over"

            battle_cmds: list[dict] = []
            battle_cmds.append(
                {
                    "code": 301,
                    "indent": 0,
                    "parameters": [0, troop_id, event.escape_allowed, can_lose],
                }
            )
            # If Win (601) → quest_switch ON
            battle_cmds.append({"code": 601, "indent": 0, "parameters": []})
            battle_cmds.append(
                {"code": 121, "indent": 1, "parameters": [quest_sw_id, quest_sw_id, 0]}
            )
            # If Escape (602) → 아무것도 안 함 (몬스터 유지)
            battle_cmds.append({"code": 602, "indent": 0, "parameters": []})
            # If Lose (603)
            battle_cmds.append({"code": 603, "indent": 0, "parameters": []})
            if not can_lose:
                battle_cmds.append({"code": 353, "indent": 1, "parameters": []})  # Game Over
            # End branch
            battle_cmds.append({"code": 604, "indent": 0, "parameters": []})
            battle_cmds.append({"code": 0, "indent": 0, "parameters": []})

            page1 = _make_page(
                battle_cmds,
                _empty_conditions(),
                trigger=0,  # action_button (through=False → 이동 차단, 접촉 시 자동 발동)
                character_name=event.battle_character_name,
                character_index=event.battle_character_index,
                through=False,
                priority=1,
                move_type=1,
                move_speed=random.randint(3, 5),
            )

        # ── Page 2: 보물상자 ─────────────────────────────────────────────────
        item_id = self.resolve_item_id(event.item, event.item_type)
        chest_cmds = self._build_quest_chest_commands(
            item_id=item_id,
            item_type=event.item_type,
            amount=event.amount,
            chest_switch=event.chest_switch,
            dialogue_before=event.dialogue_before,
            dialogue_after=event.dialogue_after,
        )

        page2 = _make_page(
            chest_cmds,
            _make_switch_condition(quest_sw_id),
            trigger=0,  # action_button
            character_name=event.chest_character_name,
            character_index=event.chest_character_index,
            direction_fix=True,
        )

        chest_sw_id = self.resolve_switch_id(event.chest_switch)
        page3 = _make_page(
            [{"code": 0, "indent": 0, "parameters": []}],
            _make_switch_condition(chest_sw_id),
            trigger=0,
            character_name="",
            character_index=0,
            through=True,
            priority=0,
        )

        return _make_event(event.name, event.x, event.y, [page1, page2, page3])


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
            current = (
                current[current.find(" ", max_chars) + 1 :]
                if " " in current[max_chars:]
                else current[max_chars:]
            )
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
    direction_fix: bool = False,
    priority: int = 1,
    walk_anime: bool = True,
    step_anime: bool = False,
    character_name: str = "",
    character_index: int = 0,
    through: bool = False,
    move_type: int = 0,
    move_speed: int = 3,
    move_frequency: int = 3,
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
        "moveFrequency": move_frequency,
        "moveRoute": {
            "list": [{"code": 0, "parameters": []}],
            "repeat": True,
            "skippable": False,
            "wait": False,
        },
        "moveSpeed": move_speed,
        "moveType": move_type,
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
