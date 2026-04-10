"""event_filler 프롬프트 — 이벤트 뼈대의 대사를 채운다.

YAML 전체를 다시 출력하지 않고, 번호별 대사만 간결하게 요청한다.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec

_SYSTEM = """\
당신은 RPG 대사 작가입니다.
각 이벤트의 빈 대사를 자연스러운 한국어 게임 대사로 작성해주세요.

## 규칙
1. 각 대사는 1~2문장. 마침표/느낌표/물음표로 끝맺음.
2. NPC 역할에 맞는 어투 사용.
3. 스위치 이름이나 시스템 용어(switch, _FILL_ 등)를 대사에 포함하지 마세요.
4. 대사 맥락:
   - dialogue (기본 대사): NPC를 처음 만났을 때. 퀘스트 부여, 상황 설명, 조언 등.
   - hint_dialogue (힌트): 퀘스트를 수락했지만 아직 완료하지 못했을 때. 간접 힌트만.
   - alt_dialogue (보상/완료): 퀘스트를 완료했을 때. 감사, 축하, 보상 안내.
   - blocked_dialogue (차단): 조건 미충족 시 짧은 안내. "아직 ~하지 않았습니다" 형태.
   - shop dialogue (상점): 상점 NPC의 인사말. 1문장.

## 출력 형식
번호와 필드명으로만 응답하세요. 설명 불필요.
```
1.dialogue: 대사 내용
1.hint_dialogue: 힌트 내용
1.alt_dialogue: 보상 내용
2.dialogue: 대사 내용
3.blocked_dialogue: 차단 내용
```
"""


def build_event_filler_prompt(
    map_spec: MapSpec,
    game_spec: GameSpec,
    skeleton_yaml: str,
) -> list[BaseMessage]:
    """event_filler LLM 프롬프트 생성.

    YAML 전체 재출력 대신, 번호별로 채워야 할 대사만 요청한다.
    skeleton_yaml은 이제 간결한 대사 요청 리스트 형태.
    """
    human = f"""\
## 게임 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}

## 맵: {map_spec.name} ({map_spec.map_type})
분위기: {map_spec.atmosphere}

## 채워야 할 대사 목록
{skeleton_yaml}

위 번호별로 대사를 작성해주세요. 번호와 필드명을 그대로 유지하고 대사만 채워주세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
