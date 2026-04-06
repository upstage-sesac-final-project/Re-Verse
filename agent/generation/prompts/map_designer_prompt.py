"""D 노드 (map_designer) 프롬프트.

canonical: docs/The_world/map_generation.md §D
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §4.D
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.generation.models import GameSpec
from agent.generation.registry.id_table import IdTable

_SYSTEM = """\
당신은 RPG Maker MZ 맵 설계사입니다.
게임 스펙을 받아 각 맵의 고수준 명세를 JSON으로 생성합니다.

## 맵 크기 규칙 (반드시 준수)
- town:    width=30, height=30, tileset_id=1, bgm="Town1"
- dungeon: width=40, height=30, tileset_id=2, bgm="Dungeon1"
- boss:    width=20, height=20, tileset_id=2, bgm="Boss1"
- field:   width=40, height=30, tileset_id=1, bgm="Field1"

## landmark position_hint 허용값
"north", "south", "east", "west",
"north-center", "south-center", "east-center", "west-center", "center"

## landmark_type 허용값
"building", "exit", "decoration"

## exit direction 허용값
"north", "south", "east", "west"

## 필수 규칙
1. 각 맵에 exit이 1개 이상 (고립 맵 금지)
2. spawn_point는 반드시 walkable 타일 (외곽 벽 기준 3칸 이상 안쪽)
3. map_id는 id_table의 값을 사용
4. town 맵: landmark에 building 2개 이상 포함
5. boss 맵: landmark에 exit 없음 (엔딩 이벤트로 처리)
"""


def build_map_designer_prompt(
    spec: GameSpec,
    id_table: IdTable,
) -> list[BaseMessage]:
    map_lines = [
        f"  - map_id={id_table.maps.get(m.name, 0)}, name={m.name}, "
        f"type={m.type}, connects_to={m.connects_to}"
        for m in spec.maps
    ]

    human = f"""## 게임 정보
제목: {spec.title}
테마: {spec.theme}
시놉시스: {spec.story.get("synopsis", "") if isinstance(spec.story, dict) else ""}

## 맵 목록 (모두 생성하세요)
{chr(10).join(map_lines)}

## 주요 NPC/캐릭터 참고
{", ".join(c.name for c in spec.characters)}

## 적 위치 참고
{", ".join(f"{e.name}({e.tier}, {e.location})" for e in spec.enemies)}

위 모든 맵의 MapSpec을 JSON 배열로 생성하세요.
각 맵의 크기(width/height/tileset_id)는 반드시 규칙대로 설정하세요.
"""
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
