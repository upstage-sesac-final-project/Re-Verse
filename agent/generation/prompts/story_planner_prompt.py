"""F 노드 — story_planner 프롬프트 빌더.

canonical: docs/The World/event/story_driven_event_plan.md §5
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec
from agent.generation.registry.id_table import IdTable
from agent.generation.registry.switch_table import SwitchTable

_SYSTEM = """\
당신은 RPG 스토리 디렉터입니다.
게임 전체 스토리를 맵별로 배분하여 이벤트 기획자(event_planner)가 참고할 스크립트를 작성합니다.

## 규칙

1. NPC 이름은 반드시 제공된 주인공 이름 목록과 달라야 합니다.
   — 주인공 이름이 "루나"라면, 어떤 NPC도 "루나"로 이름 짓지 마세요.
2. 같은 NPC가 여러 맵에 등장할 수 있습니다 (이름 일관성 유지).
3. story_flags는 반드시 제공된 스위치 목록에 있는 이름만 사용하세요.
4. required_events는 event_planner가 어떤 이벤트를 만들어야 하는지 구체적인 지시사항으로 작성하세요.
   예: "촌장 NPC와의 대화 — 던전 탐험 의뢰, act_1_started 스위치 ON"
   예: "보스 전투 후 엔딩 이벤트 — game_cleared 스위치 ON, 타이틀로 귀환"
5. 3막 구조에 따라 act_index를 맵 타입과 흐름에 맞게 배분하세요.
   - 1막(0): town — 출발, 배경 소개, NPC와 대화로 여정 시작
   - 2막(1): dungeon / field — 위기, 갈등, 단서 획득
   - 3막(2): boss — 클라이막스, 최종 전투, 결말
6. NPC의 before_dialogue(보스 처치 전)와 after_dialogue(보스 처치 후)를 구분하여 작성하세요.
   after_dialogue가 있으면 condition_switch에 적절한 스위치 이름을 지정하세요.
7. 맵당 NPC는 최대 3명까지만 지정하세요 (보스맵은 0명도 가능).
8. 모든 맵(제공된 map_id 전체)에 대해 스크립트를 생성해야 합니다.
9. 대사(before_dialogue/after_dialogue) 각 항목은 자연스러운 한 문장 단위로 작성하세요.
   문장은 마침표·느낌표·물음표로 끝맺음하여 의미가 완결되도록 하세요.
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

    maps_text = "\n".join(
        f"  map_id={s.map_id} | 이름={s.name} | 타입={s.map_type} | 분위기={s.atmosphere}"
        for s in map_specs
    )

    switches_text = ", ".join(switch_table.switches.keys()) if switch_table.switches else "없음"

    human = f"""\
## 게임 기본 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}

## 3막 구조
{acts_text if acts_text else "  (막 정보 없음)"}

## 주인공(액터) 이름 목록 — NPC 이름으로 절대 사용 금지
{actor_names}

## 맵 목록 (모든 map_id에 대해 스크립트 생성 필수)
{maps_text}

## 사용 가능한 스위치 이름 (story_flags는 이 목록에서만 선택)
{switches_text}

위 정보를 바탕으로 각 맵의 스토리 스크립트를 작성하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
