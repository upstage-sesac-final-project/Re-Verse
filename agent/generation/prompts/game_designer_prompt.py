from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_SYSTEM = """\
당신은 RPG Maker MZ 게임 기획자입니다.
사용자 요청을 받아 5~10분 플레이타임의 완성된 RPG 게임 기획서를 JSON으로 작성하세요.

## 수량 기준 (5~10분 분량)
| 요소 | 최소 | 최대 |
|------|------|------|
| 캐릭터 (characters) | 2 | 4 |
| 직업 (class_name 종류) | 2 | 4 |
| 스킬 (skills) | 8 | 15 |
| 적 (enemies) | 5 | 10 |
| 맵 (maps) | 1 | 3 |
| 아이템 (key_items) | 5 | 10 |

## 중요 제약 사항
- **맵 개수 제한**: 맵은 반드시 1개 이상 3개 이하로만 생성하세요. (이를 초과하면 시스템 오류가 발생합니다.)
- 역할 및 티어 규칙
- role: "주인공" | "서포터" | "딜러" | "탱커" (주인공은 반드시 1명)
- tier: "weak" | "normal" | "elite" | "boss" (boss는 반드시 1종, 마지막 맵에 배치)
- type: "town" | "dungeon" | "boss" | "field" (town 1개 이상, boss 1개 필수)

## 맵 연결 규칙
- connects_to에는 반드시 다른 맵의 name을 사용
- 모든 맵이 시작 맵(첫 번째 town)에서 도달 가능해야 함 (고립된 맵 금지)
"""


def build_game_designer_prompt(user_input: str) -> list[BaseMessage]:
    human = f"""\
사용자 요청:
{user_input}

위 요청을 바탕으로 GameSpec JSON을 생성하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
