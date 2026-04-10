"""event_filler 프롬프트 — 이벤트 뼈대의 대사를 채운다."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec

_SYSTEM = """\
당신은 RPG 대사 작가입니다.
이벤트 뼈대의 빈 대사(_FILL_)를 자연스러운 한국어 게임 대사로 채워주세요.

## 규칙
1. _FILL_ 부분만 대체하세요. 다른 필드(x, y, switch, item 등)는 절대 변경하지 마세요.
2. 각 대사는 1~2문장, 마침표/느낌표/물음표로 끝맺음하세요.
3. NPC 역할에 맞는 어투를 사용하세요:
   - 촌장/장로: 존대, 진지한 어투
   - 상인: 친근한 어투
   - 모험가/경비병: 짧고 단호한 어투
4. 힌트 대사(hint_dialogue)는 퀘스트 목표를 간접적으로 알려주세요. 직접 스포일러 금지.
5. 보상 대사(alt_dialogue)는 감사와 축하의 느낌으로 작성하세요.
6. 차단 대사(blocked_dialogue)는 "아직 ~하지 않았습니다" 형태로 짧게 작성하세요.
7. 스위치 이름이나 시스템 용어를 대사에 포함하지 마세요. 자연스러운 게임 대사만.

## 출력 형식
YAML만 출력하세요. 설명 불필요. 기존 뼈대 그대로 유지하면서 _FILL_ 부분만 교체.
"""


def build_event_filler_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    skeleton_yaml: str,
) -> list[BaseMessage]:
    """event_filler LLM 프롬프트 생성."""
    human = f"""\
## 게임 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}

## 맵: {map_spec.name} ({map_spec.map_type})
분위기: {map_spec.atmosphere}

## 이벤트 뼈대 (_FILL_ 부분만 채워주세요)
```yaml
{skeleton_yaml}
```

위 YAML에서 _FILL_ 부분만 자연스러운 대사로 교체하고, 나머지는 그대로 출력하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
