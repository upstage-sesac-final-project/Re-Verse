"""F 노드 — story_planner 프롬프트 빌더 (B 방식: 대본 + 이벤트 체크리스트).

각 맵에 대해 자연어 대본과 구조화된 이벤트 체크리스트를 함께 생성한다.
event_planner는 체크리스트를 1:1로 이벤트로 구현하며, 창의적 해석 없이 대본을 따른다.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable

_SYSTEM = """\
당신은 RPG 스토리 대본 작가입니다.
각 맵에 대해 **자연어 대본**과 **이벤트 체크리스트**를 함께 작성합니다.
이벤트 기획자(event_planner)는 체크리스트를 1:1로 이벤트로 구현합니다.
체크리스트에 없는 이벤트는 생성되지 않습니다.

## 대본(narrative) 작성 규칙

- 2~4문장으로 이 맵의 스토리 흐름을 서술합니다.
- 등장 NPC, 획득 아이템, 다음 목적지가 자연스럽게 드러나야 합니다.
- 예: "광장에 도착한 주인공은 교장을 만난다. 교장은 개발 키트를 건네며 과제 구역으로 향하라 말한다."

## NPC(npcs) 작성 규칙

1. 맵당 최대 3명, boss 맵은 0명도 가능합니다.
2. NPC 이름은 반드시 주인공 이름 목록과 달라야 합니다.
3. dialogues는 한 문장씩, 마침표·느낌표·물음표로 끝내세요.
4. set_switch: 대화 완료 후 ON할 스위치. 반드시 아래 스위치 목록에서 선택하세요.
   - 퀘스트를 부여하거나 아이템 획득 조건이 되는 NPC에만 지정합니다.
   - **절대 금지**: `_defeated`로 끝나는 스위치, `game_cleared`, `game_over`
   - NPC 번호별로 `{맵이름}_npc1_talked`, `{맵이름}_npc2_talked` 형식이 할당되어 있습니다.

⚠️ **퀘스트 구조 핵심 원칙**:
- NPC의 set_switch가 ON되면 해당 맵의 quest_chest가 열릴 수 있게 됩니다.
- 즉, NPC와 대화 → set_switch ON → 아이템 상자 등장 → 상자와 별도 상호작용 → 아이템 획득.
- 아이템은 NPC 대화만으로 즉시 받는 것이 아니라, 상자를 직접 열어야 획득합니다.
- 던전/필드 맵에서는 퀘스트 NPC에게 먼저 대화(퀘스트 수락)를 해야 상자가 등장하도록 이야기를 구성하세요.

## 아이템 획득(acquisitions) 작성 규칙

- 맵당 1~2개, 제공된 아이템/무기/방어구 목록에서만 선택합니다.
- 같은 아이템을 여러 맵에 중복 배분하지 마세요.
- chest_switch: 획득 후 ON할 스위치. 반드시 아래 스위치 목록에서 선택하세요.
  각 아이템/무기/방어구에 대해 `{이름}_chest` 형식의 스위치가 준비되어 있습니다.
  예: 아이템 "청동 검"의 chest_switch → "청동 검_chest"
- 단계별 배분:
  - 1막(town): 기본 무기 또는 기본 방어구 1개
  - 2막(dungeon/field): 중급 아이템/무기/방어구 1~2개
  - 3막(boss): 최고급 무기 또는 방어구 1개 (보스 처치 후 보상)

## 이동(moves) 작성 규칙

- forward: 다음 맵으로 이동 (조건 있는 게이트). 맵당 **최대 1개**.
- backward: 이전 맵으로 귀환 (조건 없음). 맵당 최대 1개.
- boss 맵은 moves를 비워두세요 (엔딩으로 종료, 이동 이벤트 없음).
- forward의 게이트 조건은 코드가 이 맵의 acquisitions[].chest_switch로 자동 구성합니다.
  condition_switches 필드는 없습니다. 직접 지정하지 마세요.
- forward의 stage_dialogues: 이 맵의 **acquisitions 수와 반드시 동일한 수**로 작성하세요.
  각 대사는 해당 아이템을 아직 획득하지 못했음을 플레이어에게 알리는 힌트입니다.
  예: acquisitions이 2개면 stage_dialogues도 2개.
  예시: "먼저 도움을 주고 장비를 받으세요.", "모든 준비가 끝나야 이곳을 통과할 수 있어요."
- backward는 stage_dialogues 불필요.

⚠️ **forward move 필수 규칙**: 아래 "맵 연결 구조"에서 forward 출구가 있는 모든 맵은
반드시 해당 목적지로의 forward move를 포함해야 합니다.
forward move가 없으면 플레이어가 다음 맵으로 진행할 수 없습니다 (게임 진행 불가).
acquisitions가 0개인 경우에도 forward move를 작성하고, stage_dialogues는 빈 배열([])로 두세요.

## 보스(has_boss) 작성 규칙

- boss 맵 타입에만 has_boss: true로 설정합니다.
- boss_name: 제공된 적 목록에서 tier="boss"인 적의 이름을 사용합니다.

## 모든 맵 생성 필수

제공된 map_id 전체에 대해 MapScreenplay를 생성해야 합니다.
"""


def build_story_planner_prompt(
    game_spec: GameSpec,
    map_specs: list[MapSpec],
    id_table: IdTable,
    switch_table: SwitchTable,
) -> list[BaseMessage]:
    actor_names = ", ".join(id_table.actors.keys()) if id_table.actors else "없음"
    acts = game_spec.story.get("acts", [])
    acts_text = "\n".join(f"  {i + 1}막: {act}" for i, act in enumerate(acts))

    # 맵 목록 (타입 포함)
    game_map_types: dict[str, str] = {gm.name: gm.type for gm in game_spec.maps}  # noqa : F841
    maps_text = "\n".join(
        f"  map_id={s.map_id} | 이름={s.name} | 타입={s.map_type} | 분위기={s.atmosphere}"
        for s in map_specs
    )

    # 맵 연결 정보 (forward/backward 방향 힌트)
    map_id_to_name: dict[int, str] = {s.map_id: s.name for s in map_specs}
    map_id_to_type: dict[int, str] = {s.map_id: s.map_type for s in map_specs}
    connections_text_parts: list[str] = []
    for s in map_specs:
        exits = s.exits
        if not exits:
            connections_text_parts.append(f"  {s.name}({s.map_type}): 출구 없음")
            continue
        exit_strs: list[str] = []
        for ex in exits:
            to_name = map_id_to_name.get(ex.to_map_id, f"Map{ex.to_map_id}")
            to_type = map_id_to_type.get(ex.to_map_id, "dungeon")
            # map_id가 현재 맵보다 크면 forward (진행 방향), 작으면 backward (귀환)
            direction = "forward" if ex.to_map_id > s.map_id else "backward"
            exit_strs.append(f"{to_name}({to_type}, {direction})")
        connections_text_parts.append(f"  {s.name}({s.map_type}): {', '.join(exit_strs)}")
    connections_text = "\n".join(connections_text_parts)

    # 스위치를 카테고리별로 분류
    chest_switches = sorted(s for s in switch_table.switches if s.endswith("_chest"))
    npc_switches = sorted(s for s in switch_table.switches if s.endswith("_talked"))
    other_switches = sorted(
        s for s in switch_table.switches if not s.endswith("_chest") and not s.endswith("_talked")
    )

    chest_sw_text = "\n".join(f"  - {s}" for s in chest_switches) or "  없음"
    npc_sw_text = "\n".join(f"  - {s}" for s in npc_switches) or "  없음"
    other_sw_text = "\n".join(f"  - {s}" for s in other_switches) or "  없음"

    items_text = ", ".join(id_table.items.keys()) if id_table.items else "없음"
    weapons_text = ", ".join(id_table.weapons.keys()) if id_table.weapons else "없음"
    armors_text = ", ".join(id_table.armors.keys()) if id_table.armors else "없음"

    # 적 목록 (보스 이름 파악용)
    boss_enemies = [e for e in game_spec.enemies if e.tier == "boss"]
    boss_text = ", ".join(e.name for e in boss_enemies) if boss_enemies else "없음"

    human = f"""\
## 게임 기본 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}

## 3막 구조
{acts_text if acts_text else "  (막 정보 없음)"}

## 주인공(액터) 이름 목록 — NPC 이름으로 절대 사용 금지
{actor_names}

## 맵 목록 (모든 map_id에 대해 MapScreenplay 생성 필수)
{maps_text}

## 맵 연결 구조 (forward/backward 방향 참고)
{connections_text}

## ★ 아이템 획득 스위치 (acquisitions.chest_switch에 사용) — 아이템명과 대응
{chest_sw_text}

## ★ NPC 대화 스위치 (npcs.set_switch에 사용) — 퀘스트 부여 NPC에만 지정
{npc_sw_text}

## 기타 스위치 (참고용 — npcs.set_switch/acquisitions.chest_switch에 사용 금지)
{other_sw_text}

## 보상 배분용 아이템 목록 (앞쪽=기본, 뒤쪽=고급 — acquisitions에 사용)
아이템: {items_text}
무기:   {weapons_text}
방어구: {armors_text}

## 보스 적 이름 (has_boss=true 맵의 boss_name에 사용)
{boss_text}

위 정보를 바탕으로 각 맵의 대본과 이벤트 체크리스트를 작성하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
