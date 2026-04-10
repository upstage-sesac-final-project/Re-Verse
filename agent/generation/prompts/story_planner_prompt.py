"""F 노드 — story_planner 프롬프트 빌더.

canonical: docs/The World/event/story_driven_event_plan.md §5
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec

_SYSTEM = """\
당신은 RPG 퀘스트 기획자입니다.
게임 정보를 받아 퀘스트 계획을 JSON으로 작성합니다.

## 반드시 지켜야 할 규칙

1. 퀘스트(quests)는 메인 퀘스트 1개만 작성합니다.
2. 퀘스트 단계(steps)는 맵 순서대로 진행됩니다.
   - 첫 맵(town): type="talk", target=NPC 이름 (퀘스트 부여)
   - 중간 맵(dungeon/field): type="battle", target=적 그룹 이름 (전투)
   - 마지막 맵(boss): 포함하지 않음 (보스전은 시스템이 자동 생성)
3. 각 step의 completion_switch는 "{맵이름}_{목적}" 형식으로 작성합니다.
   예: "시작_마을_quest_accepted", "어둠의_동굴_고블린_defeated"
4. NPC 이름은 주인공(actor) 이름과 절대 겹치지 않아야 합니다.
5. 맵별 NPC는 최대 2명. 역할: "퀘스트 부여자", "상점", "힌트 제공", "가이드" 중 선택.
6. boss_name은 tier="boss"인 적의 이름입니다.
7. 각 맵의 gate_switch는 이전 맵의 완료 스위치입니다. 첫 맵은 null.
8. reward_item은 제공된 무기/아이템 목록에서 선택합니다.
9. reward_switch는 마지막 dungeon/field 맵의 완료 스위치입니다.
10. maps 목록은 제공된 맵 순서를 따릅니다. 모든 맵을 포함해야 합니다.
"""


def build_story_planner_prompt(
    game_spec: GameSpec,
    map_specs: list[MapSpec],
) -> list[BaseMessage]:
    actor_names = (
        ", ".join(c.name for c in game_spec.characters) if game_spec.characters else "없음"
    )
    acts = game_spec.story.get("acts", [])
    acts_text = "\n".join(f"  {i + 1}막: {act}" for i, act in enumerate(acts))

    maps_text = "\n".join(
        f"  {i + 1}. map_id={s.map_id} | 이름={s.name} | 타입={s.map_type} | 분위기={s.atmosphere}"
        for i, s in enumerate(map_specs)
    )

    enemies_text = "\n".join(
        f"  - {e.name} (tier={e.tier}, 위치={e.location})" for e in game_spec.enemies
    )

    items_list: list[str] = []
    if game_spec.weapons:
        items_list.extend(f"  - [무기] {w}" for w in game_spec.weapons)
    if game_spec.armors:
        items_list.extend(f"  - [방어구] {a}" for a in game_spec.armors)
    if game_spec.key_items:
        items_list.extend(f"  - [아이템] {k}" for k in game_spec.key_items)
    items_text = "\n".join(items_list) if items_list else "  (없음)"

    human = f"""\
## 게임 기본 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}

## 3막 구조
{acts_text if acts_text else "  (막 정보 없음)"}

## 주인공(액터) 이름 목록 — NPC 이름으로 절대 사용 금지
{actor_names}

## 맵 목록 (순서대로, 모든 맵에 대해 maps 항목 필수)
{maps_text}

## 적 목록 (tier로 보스 식별)
{enemies_text}

## 보상 후보 아이템/무기 목록 (reward_item 선택 시 이 목록에서)
{items_text}

위 정보를 바탕으로 GameQuestPlan JSON을 작성하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
