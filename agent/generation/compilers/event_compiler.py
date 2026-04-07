import logging
from typing import Any

from agent.generation.compilers.dsl_models import (
    BattleEvent,
    ChestEvent,
    DslEvent,
    NpcEvent,
    ShopEvent,
    TransferEvent,
)

logger = logging.getLogger(__name__)


class EventCompiler:
    def __init__(self, id_table: dict, switch_table: dict):
        self.id_table = id_table
        self.switch_table = switch_table

    def compile_event(self, dsl_event: DslEvent) -> dict[str, Any]:
        """DSL 이벤트를 RPG Maker MZ 이벤트 객체로 컴파일."""
        if isinstance(dsl_event, NpcEvent):
            return self._compile_npc(dsl_event)
        elif isinstance(dsl_event, TransferEvent):
            return self._compile_transfer(dsl_event)
        elif isinstance(dsl_event, ShopEvent):
            return self._compile_shop(dsl_event)
        elif isinstance(dsl_event, ChestEvent):
            return self._compile_chest(dsl_event)
        elif isinstance(dsl_event, BattleEvent):
            return self._compile_battle(dsl_event)
        else:
            logger.warning("미지원 이벤트 타입: %s", dsl_event.type)
            return self._stub_event(dsl_event)

    def _compile_npc(self, event: NpcEvent) -> dict[str, Any]:
        cmds = []
        # 대화창 묶음 처리
        for line in event.dialogue:
            cmds.append(
                {
                    "code": 101,
                    "indent": 0,
                    "parameters": [event.face_image, event.face_index, 0, 2, event.name],
                }
            )
            cmds.append({"code": 401, "indent": 0, "parameters": [line]})

        if event.set_switch:
            sw_id = self._resolve_switch(event.set_switch)
            cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        page = self._make_page(cmds)
        page["image"]["characterName"] = event.character_name
        page["image"]["characterIndex"] = event.character_index
        return self._make_event_json(event, [page])

    def _compile_transfer(self, event: TransferEvent) -> dict[str, Any]:
        map_id = self.id_table["maps"].get(event.to_map, 1)
        # [mode, map_id, x, y, direction, fade_type]
        cmds = [
            {"code": 201, "indent": 0, "parameters": [0, map_id, event.to_x, event.to_y, 0, 0]},
            {"code": 0, "indent": 0, "parameters": []},
        ]
        return self._make_event_json(event, [self._make_page(cmds, trigger=2)])  # player_touch=2

    def _compile_shop(self, event: ShopEvent) -> dict[str, Any]:
        cmds = []
        if event.dialogue:
            cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, event.name]})
            cmds.append({"code": 401, "indent": 0, "parameters": [event.dialogue]})

        # 첫 번째 상품 (302)
        if event.items:
            first = event.items[0]
            g_type = 0 if first.item_type == "item" else 1 if first.item_type == "weapon" else 2
            g_id = self._resolve_item(first.item, first.item_type)
            cmds.append(
                {
                    "code": 302,
                    "indent": 0,
                    "parameters": [g_type, g_id, 0, 0, 1 if event.purchase_only else 0],
                }
            )

            # 추가 상품 (605)
            for item in event.items[1:]:
                g_type = 0 if item.item_type == "item" else 1 if item.item_type == "weapon" else 2
                g_id = self._resolve_item(item.item, item.item_type)
                cmds.append({"code": 605, "indent": 0, "parameters": [g_type, g_id, 0, 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})
        return self._make_event_json(event, [self._make_page(cmds)])

    def _compile_chest(self, event: ChestEvent) -> dict[str, Any]:
        cmds = []

        if event.dialogue_before:
            cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, event.name]})
            cmds.append({"code": 401, "indent": 0, "parameters": [event.dialogue_before]})

        # 아이템 지급
        if event.item_type == "gold":
            cmds.append({"code": 125, "indent": 0, "parameters": [0, 0, event.amount]})
        else:
            item_id = self._resolve_item(event.item, event.item_type)
            code = 126 if event.item_type == "item" else 127 if event.item_type == "weapon" else 128
            params = [item_id, 0, 0, event.amount]
            if event.item_type in ("weapon", "armor"):
                params.append(False)
            cmds.append({"code": code, "indent": 0, "parameters": params})

        if event.dialogue_after:
            cmds.append({"code": 101, "indent": 0, "parameters": ["", 0, 0, 2, event.name]})
            cmds.append({"code": 401, "indent": 0, "parameters": [event.dialogue_after]})

        # 글로벌 스위치 ON
        if event.chest_switch:
            sw_id = self._resolve_switch(event.chest_switch)
            cmds.append({"code": 121, "indent": 0, "parameters": [sw_id, sw_id, 0]})

        # 셀프 스위치 A ON (one_time 제어)
        if event.one_time:
            cmds.append({"code": 123, "indent": 0, "parameters": ["A", 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        pages = [self._make_page(cmds)]

        # 2번 페이지: 상자 열린 후 — 셀프 스위치 A ON 조건, 빈 이벤트
        if event.one_time:
            opened_cond = self._make_default_conditions()
            opened_cond["selfSwitchCh"] = "A"
            opened_cond["selfSwitchValid"] = True
            pages.append(
                self._make_page(
                    [{"code": 0, "indent": 0, "parameters": []}], conditions=opened_cond
                )
            )

        return self._make_event_json(event, pages)

    def _compile_battle(self, event: BattleEvent) -> dict[str, Any]:
        troop_id = self.id_table.get("troops", {}).get(event.troop, 1)
        can_escape = 1 if event.escape_allowed else 0
        can_lose = 1 if event.lose_condition == "continue" else 0

        cmds: list[dict] = []

        # 배틀 스위치 조건으로 진입 가드
        if event.battle_switch:
            sw_id = self._resolve_switch(event.battle_switch)
            cmds.append({"code": 111, "indent": 0, "parameters": [0, sw_id, 0]})  # if switch=ON

        # 전투 처리: [0=직접지정, troopId, canEscape, canLose]
        cmds.append({"code": 301, "indent": 0, "parameters": [0, troop_id, can_escape, can_lose]})

        # 승리 분기
        cmds.append({"code": 601, "indent": 0, "parameters": []})
        for win_action in event.on_win:
            if win_action.give_item and isinstance(win_action.give_item, dict):
                i_name = win_action.give_item.get("item", "")
                i_type = win_action.give_item.get("item_type", "item")
                amount = int(win_action.give_item.get("amount", 1))
                if i_type == "gold":
                    cmds.append({"code": 125, "indent": 1, "parameters": [0, 0, amount]})
                else:
                    i_id = self._resolve_item(i_name, i_type)
                    code = 126 if i_type == "item" else 127 if i_type == "weapon" else 128
                    params = [i_id, 0, 0, amount]
                    if i_type in ("weapon", "armor"):
                        params.append(False)
                    cmds.append({"code": code, "indent": 1, "parameters": params})
            if win_action.give_exp:
                # [0=전파티, 0=증가, 0=상수, exp값, False=레벨업표시 없음]
                cmds.append(
                    {
                        "code": 315,
                        "indent": 1,
                        "parameters": [0, 0, 0, int(win_action.give_exp), False],
                    }
                )
            if win_action.set_switch:
                sw_id = self._resolve_switch(win_action.set_switch)
                cmds.append({"code": 121, "indent": 1, "parameters": [sw_id, sw_id, 0]})

        # 전투 처리 종료
        cmds.append({"code": 604, "indent": 0, "parameters": []})

        if event.battle_switch:
            cmds.append({"code": 412, "indent": 0, "parameters": []})  # End If

        # 셀프 스위치 A ON (one_time 제어)
        if event.one_time:
            cmds.append({"code": 123, "indent": 0, "parameters": ["A", 0]})

        cmds.append({"code": 0, "indent": 0, "parameters": []})

        pages = [self._make_page(cmds, trigger=1)]  # player_touch=1

        # 2번 페이지: 전투 완료 후 — 셀프 스위치 A ON, 빈 이벤트
        if event.one_time:
            done_cond = self._make_default_conditions()
            done_cond["selfSwitchCh"] = "A"
            done_cond["selfSwitchValid"] = True
            pages.append(
                self._make_page([{"code": 0, "indent": 0, "parameters": []}], conditions=done_cond)
            )

        return self._make_event_json(event, pages)

    def _resolve_switch(self, name: str) -> int:
        return self.switch_table["switches"].get(name, 1)

    def _resolve_item(self, name: str, item_type: str) -> int:
        cat = "items" if item_type == "item" else "weapons" if item_type == "weapon" else "armors"
        return self.id_table.get(cat, {}).get(name, 1)

    def _make_default_conditions(self) -> dict:
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
        self, cmds: list[dict], trigger: int = 0, conditions: dict | None = None
    ) -> dict:
        return {
            "conditions": conditions if conditions is not None else self._make_default_conditions(),
            "list": cmds,
            "trigger": trigger,
            "image": {
                "characterIndex": 0,
                "characterName": "",
                "direction": 2,
                "pattern": 0,
                "tileId": 0,
            },
            "moveSpeed": 3,
            "moveFrequency": 3,
            "moveRoute": {
                "list": [{"code": 0, "parameters": []}],
                "repeat": True,
                "skippable": False,
                "wait": False,
            },
            "moveType": 0,
            "priorityType": 1,
            "stepAnime": False,
            "walkAnime": True,
        }

    def _make_event_json(self, dsl_event: Any, pages: list[dict]) -> dict:
        return {
            "id": 0,
            "name": dsl_event.name,
            "note": "",
            "x": dsl_event.x,
            "y": dsl_event.y,
            "pages": pages,
        }

    def _stub_event(self, dsl_event: Any) -> dict:
        return self._make_event_json(dsl_event, [self._make_page([{"code": 0, "parameters": []}])])
