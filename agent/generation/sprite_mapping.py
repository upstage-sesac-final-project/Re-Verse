"""스프라이트 매핑 — 적/NPC 맵 위 이미지 자동 결정.

event_planner.py에서 분리. battlerName → (character_name, character_index) 매핑.
기존 로직 100% 유지.
"""

import logging

from agent.generation.compilers.dsl_models import BattleEvent
from agent.generation.models import GameSpec
from agent.generation.registry.id_table import IdTable

logger = logging.getLogger(__name__)

_SF_KEYWORDS = ("sf", "sci-fi", "science", "사이버", "로봇", "우주", "미래")


def _build_troop_sprite_map(
    game_spec: GameSpec,
    id_table: IdTable,
    generated_assets: dict,
) -> dict[str, tuple[str, int]]:
    """id_table.troops의 모든 troop_name에 대해 (character_name, character_index)를 사전 결정.

    id_table.troops는 spec 기준 exact key이므로 런타임 문자열 파싱 없이 바로 사용 가능.
    우선순위:
      0순위: battlerName fallback 적 → Nature/1
      1순위: battlerName → _BATTLER_TO_MAP_SPRITE 직접 조회
      2순위: tier 기반 폴백
    """
    # Enemies.json에서 enemy_id → battlerName 구성
    enemies_json: list = generated_assets.get("Enemies.json") or []
    enemy_id_to_battler: dict[int, str] = {
        e["id"]: e["battlerName"]
        for e in enemies_json
        if e and isinstance(e, dict) and e.get("id") and e.get("battlerName")
    }
    # fallback 처리된 적 ID (note에 "(fallback)" 포함)
    fallback_enemy_ids: set[int] = {
        e["id"]
        for e in enemies_json
        if e and isinstance(e, dict) and e.get("id") and "(fallback)" in (e.get("note") or "")
    }

    # spec_enemy_name → battlerName / tier
    enemy_tier: dict[str, str] = {e.name: e.tier for e in game_spec.enemies}
    battler_map: dict[str, str] = {
        name: enemy_id_to_battler[eid]
        for name, eid in id_table.enemies.items()
        if eid in enemy_id_to_battler
    }
    fallback_enemy_names: set[str] = {
        name for name, eid in id_table.enemies.items() if eid in fallback_enemy_ids
    }
    is_sf = any(k in game_spec.theme.lower() for k in _SF_KEYWORDS)

    result: dict[str, tuple[str, int]] = {}
    for troop_name, troop_id in id_table.troops.items():
        # troop_name에서 spec enemy name 추출 (id_table 기준이므로 항상 정확)
        if "×" in troop_name:
            spec_name = troop_name.rsplit("×", 1)[0]
        elif troop_name.endswith("_단독"):
            spec_name = troop_name[: -len("_단독")]
        else:
            spec_name = troop_name

        # 0순위: fallback → Nature/1
        if spec_name in fallback_enemy_names:
            result[troop_name] = ("Nature", 1)
            continue

        # 1순위: battlerName 테이블 조회
        battler_name = battler_map.get(spec_name)
        if battler_name and battler_name in _BATTLER_TO_MAP_SPRITE:
            result[troop_name] = _BATTLER_TO_MAP_SPRITE[battler_name]
            continue

        # 2순위: tier 기반 폴백
        tier = enemy_tier.get(spec_name, "normal")
        if is_sf:
            char_name = "SF_Monster"
            char_idx = (6 + troop_id % 2) if tier in ("boss", "elite") else troop_id % 6
        elif tier == "boss":
            char_name = f"$BigMonster{1 + troop_id % 2}"
            char_idx = 0
        else:
            char_name = "Evil"
            char_idx = 7
        result[troop_name] = (char_name, char_idx)

    return result


# battlerName → (character_name, character_index)
# 직접 이미지 확인 기반 시각적 매핑 테이블
# characters/Monster.png 레이아웃:  0=파란피부언데드여, 1=초록몬스터, 2=은회색늑대인간, 3=검은번개갑옷,
#                                   4=흰여우구미호, 5=검은뿔소악마, 6=금관좀비보스, 7=보라악마날개보스
# characters/Evil.png 레이아웃:     0=초록두건고글불량배, 1=갈색안경학자악당, 2=흰은발여성마법사,
#                                   3=황금가면마왕, 6=황금갑옷기사, 7=갈색로브흑막
# characters/$BigMonster1.png:      4캐릭터×3프레임, 3개씩 묶음
#   0~2=보라마왕마법사, 3~5=초록나무괴물, 6~8=보라곤충두족류(크라켄), 9~11=다머리초록용(히드라)
# characters/$BigMonster2.png:      4캐릭터×3프레임, 3개씩 묶음
#   0~2=붉은드래곤, 3~5=황금천마기사, 6~8=보라촉수여신(이블갓), 9~11=붉은변이악마
# characters/SF_Monster.png 레이아웃: 0=흰정장마피아, 1=검은군복요원, 2=검은그림자빨간눈,
#                                     3=빨간광대, 4=파란메카로봇, 5=검은육중전투로봇,
#                                     6=보라리치, 7=붉은도깨비장군
_BATTLER_TO_MAP_SPRITE: dict[str, tuple[str, int]] = {
    # ── 판타지: Monster 시트 ────────────────────────────────────────────
    "Zombie": ("Monster", 1),
    "Caitsith": ("Monster", 0),
    "Undine": ("Monster", 0),
    "Goblin": ("Monster", 1),
    "Matango": ("Monster", 1),
    "Gnome": ("Monster", 1),
    "Oddegg": ("Monster", 1),
    "Frilledlizard": ("Monster", 1),
    "Wolfman": ("Monster", 2),
    "Tigerbunny": ("Monster", 2),
    "Birdman": ("Monster", 2),
    "Hakutaku": ("Monster", 2),
    "Plasma": ("Monster", 3),
    "Sandworm": ("Monster", 3),
    "Mechascorpion": ("Monster", 3),
    "Machinerybee": ("Monster", 3),
    "Salamander": ("Monster", 3),
    "Foxman": ("Monster", 4),
    "Sylph": ("Monster", 4),
    "Harpy": ("Monster", 4),
    "Unicorn": ("Monster", 4),
    "Petitdevil": ("Monster", 5),
    "Crow": ("Monster", 5),
    "Crab": ("Monster", 5),
    "Demonpot": ("Monster", 5),
    "Evilbook": ("Monster", 5),
    "Mimic": ("Monster", 5),
    "Wraith": ("Monster", 6),
    "Gatekeeper": ("Monster", 6),
    "Hi_monster": ("Monster", 6),
    "Demoncount": ("Monster", 7),
    # ── 판타지: Evil 시트 ───────────────────────────────────────────────
    "Mercenary": ("Evil", 0),
    "Sailor": ("Evil", 0),
    "Witch": ("Evil", 2),
    "Medusa": ("Evil", 2),
    "Siren": ("Evil", 2),
    "Sorcerer": ("Evil", 3),
    "Berserker": ("Evil", 4),
    "Darkelf": ("Evil", 5),
    "Highking": ("Evil", 6),
    "Captain": ("Evil", 6),
    "Blackknight": ("Evil", 6),
    "Stoneknight": ("Evil", 6),
    # ── 판타지: $BigMonster1 (대형, 4캐릭터×3프레임 — 3개씩 묶음) ──────────
    # index 0~2:  보라 마왕형 마법사
    "Lich": ("$BigMonster1", 0),
    "Goddess_of_death": ("$BigMonster1", 0),
    # index 3~5:  초록 나무 괴물
    "Treant": ("$BigMonster1", 3),
    # index 6~8:  보라 곤충/두족류 (크라켄형)
    "Kraken": ("$BigMonster1", 6),
    "Ketos": ("$BigMonster1", 6),
    # index 9~11: 다머리 초록 용 (히드라형)
    "Hydra": ("$BigMonster1", 9),
    # ── 판타지: $BigMonster2 (대형, 4캐릭터×3프레임 — 3개씩 묶음) ──────────
    # index 0~2:  붉은 드래곤
    "Dragon": ("$BigMonster2", 0),
    "Demon": ("$BigMonster2", 0),
    # index 3~5:  황금+날개 천마 기사
    "God_of_light": ("$BigMonster2", 3),
    "Goddess": ("$BigMonster2", 3),
    # index 6~8:  보라+촉수 여신형
    "Evilgod": ("$BigMonster2", 6),
    # index 9~11: 붉은 변이 악마 (최종 보스)
    "Demon_metamorphosis": ("$BigMonster2", 9),
    # ── SF: SF_Monster 시트 ─────────────────────────────────────────────
    "SF_Boss": ("SF_Monster", 0),
    "SF_Madscientist": ("SF_Monster", 0),
    "SF_Agent": ("SF_Monster", 1),
    "SF_Mafia": ("SF_Monster", 1),
    "SF_Specialforces": ("SF_Monster", 1),
    "SF_Armygorilla": ("SF_Monster", 1),
    "SF_Armymonkey": ("SF_Monster", 1),
    "SF_Brownbear": ("SF_Monster", 1),
    "SF_Shadow": ("SF_Monster", 2),
    "SF_Zombiedog": ("SF_Monster", 2),
    "SF_Wolf": ("SF_Monster", 2),
    "SF_Whitewolf": ("SF_Monster", 2),
    "SF_Anaconda": ("SF_Monster", 2),
    "SF_Kamaitachi": ("SF_Monster", 2),
    "SF_Will_o_the_wisp": ("SF_Monster", 2),
    "SF_Jiangshi": ("SF_Monster", 2),
    "SF_Madclown": ("SF_Monster", 3),
    "SF_Hannyamask": ("SF_Monster", 3),
    "SF_Talkingmuppet": ("SF_Monster", 3),
    "SF_Evilteddybear": ("SF_Monster", 3),
    "SF_Kappa": ("SF_Monster", 3),
    "SF_Workrobot": ("SF_Monster", 4),
    "SF_Drone": ("SF_Monster", 4),
    "SF_Timebomb": ("SF_Monster", 4),
    "SF_Mechasphere": ("SF_Monster", 4),
    "SF_Slaughterrobot": ("SF_Monster", 5),
    "SF_Securityrobot": ("SF_Monster", 5),
    "SF_Cyborg": ("SF_Monster", 5),
    "SF_Enmadaio": ("SF_Monster", 6),
    "SF_Hermit": ("SF_Monster", 6),
    "SF_Demon_of_universe": ("SF_Monster", 6),
    "SF_Skullmask": ("SF_Monster", 6),
    "SF_Phoenix": ("SF_Monster", 6),
    "SF_Redogre": ("SF_Monster", 7),
    "SF_Blueogre": ("SF_Monster", 7),
}


def _fix_battle_sprites(
    events: list,
    troop_to_sprite: dict[str, tuple[str, int]],
) -> list:
    """BattleEvent의 map sprite를 사전 구성된 troop_to_sprite 테이블로 결정."""
    for event in events:
        if not isinstance(event, BattleEvent):
            continue
        sprite = troop_to_sprite.get(event.troop)
        if sprite:
            event.character_name, event.character_index = sprite
        else:
            logger.warning("troop '%s' sprite 매핑 없음 → 기본값 유지", event.troop)
    return events
