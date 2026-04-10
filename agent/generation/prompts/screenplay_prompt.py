"""각본(screenplay) 프롬프트 — LLM에게 게임 전체 각본을 요청한다.

영화 대본 형식으로 NPC 대사, 전투, 이동 조건, 보상을 모두 포함.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec, MapSpec
from agent.generation.registry.id_table import IdTable

_SYSTEM = """\
당신은 RPG 게임 시나리오 작가입니다.
게임 정보를 받으면 맵별로 완전한 스토리 각본을 작성합니다.

## 규칙

1. 각 맵을 Scene으로 작성합니다.
2. NPC는 3가지 상태의 대사를 작성합니다:
   - 첫 만남: 퀘스트 부여, 상황 설명 (이 맵에서 무엇을 해야 하는지)
   - 진행 중: 간접 힌트 (직접 스포일러 금지, 적의 약점이나 방향만 암시)
   - 완료 후: 감사, 보상 안내, 다음 맵으로의 동기부여
3. **전투 승리 보상은 반드시 무기/방어구/소모품 목록에서 선택**하세요. 키아이템은 보상으로 사용하지 마세요.
4. 이동 조건을 명시합니다 (어떤 조건을 충족해야 다음 맵으로 갈 수 있는지).
5. 차단 대사를 작성합니다 (조건 미충족 시 NPC나 문이 하는 말).
6. 상점 NPC의 인사말을 작성합니다. **상점은 town 맵에만 1개.**
7. **보스 맵에서는 반드시 "보스전:" 형식**을 사용하세요 ("전투:" 아님).
8. 대사는 1~2문장. 한국어. 마침표/느낌표/물음표로 끝.
9. 스위치, 변수, 시스템 용어를 대사에 포함하지 마세요.
10. NPC 이름은 주인공 이름과 겹치지 않아야 합니다.
11. **각 NPC에 고유한 말투**를 부여하세요:
    - 촌장/장로: 존대, 무게감 ("~하시오", "~하시게")
    - 요정/정령: 신비롭고 부드러운 ("~일 거예요", "~답니다")
    - 전사/경비병: 짧고 단호한 ("~해라", "~이다")
    - 상인: 친근하고 활기찬 ("~해요!", "~있답니다!")
12. **Scene마다 분위기를 전환**하세요: 평화(town) → 긴장(field) → 위험(dungeon) → 결전(boss)

## 출력 형식 (반드시 이 형식을 지켜주세요)

각 Scene을 아래 형식으로 작성합니다:

```
## Scene {번호}: {맵 이름}

[배경: 1~2줄 상황 묘사]

NPC {NPC이름} ({역할}):
  첫만남: "{대사}"
  진행중: "{힌트 대사}"
  완료후: "{보상 대사}"

NPC {NPC이름} (상점):
  인사: "{인사말}"

전투: {적 그룹 이름}
  승리보상: {아이템 이름}

전투: {적 그룹 이름}
  승리보상: 없음

이동조건: {어떤 조건} 충족 시 → {다음 맵 이름}
차단대사: "{조건 미충족 시 대사}"

보스전: {보스 적 그룹 이름}
  전투전: "{긴장감 대사}"
  승리후: "{축하/엔딩 대사}"
```

상점은 town 맵에만 1개. 다른 맵에는 상점 NPC를 넣지 마세요.
전투가 없는 맵(town)은 전투를 생략하세요.
보스전은 boss 맵에서만 작성하세요.

⚠️ 중요: boss 맵의 최종 보스 전투는 반드시 "보스전:" 으로 시작하세요.
"전투:" 로 쓰면 일반 전투로 처리되어 엔딩이 발동하지 않습니다.
⚠️ 전투 승리 보상에 키아이템(열쇠, 크리스탈 등) 대신 무기/방어구를 넣으세요.
"""


def build_screenplay_prompt(
    game_spec: GameSpec,
    map_specs: list[MapSpec],
    id_table: IdTable,
) -> list[BaseMessage]:
    """각본 생성 프롬프트."""
    # 캐릭터 정보
    actors = ", ".join(f"{c.name}({c.class_name})" for c in game_spec.characters)

    # 적 정보 (tier 포함)
    enemies_text = "\n".join(f"- {e.name} ({e.tier}, {e.location})" for e in game_spec.enemies)

    # 아이템/무기/방어구
    items = ", ".join(list(id_table.items.keys())[:10])
    weapons = ", ".join(list(id_table.weapons.keys())[:10])
    armors = ", ".join(list(id_table.armors.keys())[:10])

    # 적 그룹 (troop) 목록
    troops = ", ".join(list(id_table.troops.keys())[:15])

    # 맵 목록
    maps_text = "\n".join(
        f"{i + 1}. {s.name} ({s.map_type}) — {s.atmosphere}" for i, s in enumerate(map_specs)
    )

    # 보스 이름
    boss = next((e.name for e in game_spec.enemies if e.tier == "boss"), "보스")

    human = f"""\
## 게임 정보
제목: {game_spec.title}
테마: {game_spec.theme}
시놉시스: {game_spec.story.get("synopsis", "")}
스토리 구조: {" → ".join(game_spec.story.get("acts", []))}

## 캐릭터 (주인공 — NPC 이름으로 사용 금지)
{actors}

## 적
{enemies_text}

## 사용 가능한 적 그룹 (전투에 반드시 이 이름 사용)
{troops}

## 아이템
무기: {weapons}
방어구: {armors}
소모품/키아이템: {items}

## 맵 (순서대로 — 모든 맵에 대해 Scene 작성 필수)
{maps_text}

## 최종 보스
{boss}

각 맵에 대해 NPC 대화(첫만남/진행중/완료후), 전투, 이동조건, 보상을 포함한 각본을 작성하세요.
town 맵에는 전투 없이 NPC와 상점만, dungeon/field에는 전투+NPC, boss에는 보스전을 배치하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
