import json
import logging
import os
from typing import Any

from agent.generation.state import GenerationState
from agent.utils.game_data_io import load_temp_data

logger = logging.getLogger(__name__)


async def integrator_node(state: GenerationState) -> GenerationState:
    """H. 통합기 노드: 생성된 모든 데이터를 RPG Maker MZ 프로젝트 형식으로 조립 및 파일 저장."""
    logger.info("--- NODE: integrator ---")

    game_id = state["game_id"]
    game_spec = state.get("game_spec")
    if game_spec is None:
        raise ValueError("game_spec is missing in state")

    assets = state.get("generated_assets", {})
    map_specs = state.get("map_specs", [])

    # 0. 경로 설정
    base_path = os.path.join("storage", "games", game_id, "data")
    os.makedirs(base_path, exist_ok=True)

    # 1. 에셋 파일 저장
    for fname, data in assets.items():
        file_path = os.path.join(base_path, fname)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

    # 2. Map*.json 저장 및 MapInfos 생성 데이터 준비
    map_infos: list[Any] = [None]  # Fix mypy arg-type error
    map_ids = sorted([int(m["map_id"]) for m in map_specs])

    for map_id in map_ids:
        # [핵심] 임시 파일에서 타일 및 이벤트 로드
        tiles = load_temp_data(game_id, "tiles", map_id) or ([0] * 30 * 30 * 6)
        raw_events = load_temp_data(game_id, "events", map_id) or []

        # RPG Maker MZ는 event.id == 배열 인덱스여야 함
        events = []
        for i, evt in enumerate(raw_events, start=1):
            if evt is not None and isinstance(evt, dict):
                evt["id"] = i
            events.append(evt)

        fname = f"Map{map_id:03d}.json"
        spec_dict = next((m for m in map_specs if int(m["map_id"]) == map_id), None)

        bgm_name = spec_dict.get("bgm", "Town1") if spec_dict else "Town1"
        width = int(spec_dict.get("width", 30)) if spec_dict else 30
        height = int(spec_dict.get("height", 30)) if spec_dict else 30
        tileset_id = int(spec_dict.get("tileset_id", 1)) if spec_dict else 1
        display_name = spec_dict.get("name", "Map") if spec_dict else "Map"

        map_content = {
            "autoplayBgm": True,
            "autoplayBgs": False,
            "battleback1Name": "",
            "battleback2Name": "",
            "bgm": {"name": bgm_name, "volume": 90, "pitch": 100, "pan": 0},
            "bgs": {"name": "", "volume": 90, "pitch": 100, "pan": 0},
            "disableDashing": False,
            "displayName": display_name,
            "encounterList": [],
            "encounterStep": 30,
            "height": height,
            "note": "",
            "parallaxLoopX": False,
            "parallaxLoopY": False,
            "parallaxName": "",
            "parallaxShow": False,
            "parallaxSx": 0,
            "parallaxSy": 0,
            "scrollType": 0,
            "specifyBattleback": False,
            "tilesetId": tileset_id,
            "width": width,
            "data": tiles,
            "events": [None] + events,
        }

        with open(os.path.join(base_path, fname), "w", encoding="utf-8") as f:
            json.dump(map_content, f, ensure_ascii=False, indent=4)

        map_infos.append(
            {
                "id": map_id,
                "expanded": False,
                "name": display_name,
                "order": map_id,
                "parentId": 0,
                "scrollX": 0,
                "scrollY": 0,
            }
        )

    # 3. MapInfos.json 저장
    with open(os.path.join(base_path, "MapInfos.json"), "w", encoding="utf-8") as f:
        json.dump(map_infos, f, ensure_ascii=False, indent=4)

    # 4. System.json 패치
    system_path = os.path.join(base_path, "System.json")
    if os.path.exists(system_path):
        with open(system_path, encoding="utf-8") as f:
            system_data = json.load(f)
    else:
        system_data = {"advanced": {"gameId": 12345}, "partyMembers": [1]}

    first_map_id = map_ids[0] if map_ids else 1

    # [핵심] 투명도 옵션 강제 해제
    system_data["optTransparent"] = False
    system_data["gameTitle"] = game_spec.get("title", "Re:Verse Game")
    system_data["startMapId"] = first_map_id
    system_data["startX"] = 8
    system_data["startY"] = 6

    st = state.get("switch_table")
    if st is not None:
        system_data["switches"] = [""] + list(st.get("switches", {}).keys())
        system_data["variables"] = [""] + list(st.get("variables", {}).keys())

    # 1번 액터가 파티에 있도록 보장
    if not system_data.get("partyMembers"):
        system_data["partyMembers"] = [1]
    elif 1 not in system_data["partyMembers"]:
        system_data["partyMembers"].insert(0, 1)

    with open(system_path, "w", encoding="utf-8") as f:
        json.dump(system_data, f, ensure_ascii=False, indent=4)

    # 5. Actors.json 보정
    actors_path = os.path.join(base_path, "Actors.json")
    valid_character_images = [
        "Actor1",
        "Actor2",
        "Actor3",
        "People1",
        "People2",
        "People3",
        "People4",
        "SF_Actor1",
        "SF_Actor2",
        "SF_Actor3",
        "SF_People1",
        "SF_People2",
        "SF_People3",
        "Evil",
        "Monster",
        "Nature",
    ]

    if os.path.exists(actors_path):
        try:
            with open(actors_path, encoding="utf-8") as f:
                actors_data = json.load(f)

            modified = False
            for actor in actors_data:
                if actor and isinstance(actor, dict):
                    cname = actor.get("characterName")
                    if not cname or cname not in valid_character_images:
                        actor["characterName"] = "Actor1"
                        actor["characterIndex"] = actor.get("characterIndex", 0) % 8
                        modified = True

                    fname = actor.get("faceName")
                    if not fname or fname not in valid_character_images:
                        actor["faceName"] = "Actor1"
                        actor["faceIndex"] = actor.get("characterIndex", 0)
                        modified = True

            if modified:
                with open(actors_path, "w", encoding="utf-8") as f:
                    json.dump(actors_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logger.error(f"Actors.json 보정 실패: {e}")

    return {
        **state,
        "completed_phases": state.get("completed_phases", []) + ["integrated"],
        "current_phase": "integrated",
    }
