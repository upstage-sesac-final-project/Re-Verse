"""사용자 쿼리 → MapIntent 추출.

Solar(structured output, json_schema)로 한 번 호출한다.
"""

import logging
from typing import cast

from langchain_core.messages import HumanMessage, SystemMessage

from agent.core.llm_client import invoke_llm
from agent.generation.mapgen.intent.schema import MapIntent

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """당신은 RPG 맵 생성 어시스턴트입니다.
사용자가 만들고 싶은 게임/맵 설명을 받아 구조화된 MapIntent로 변환합니다.

규칙:
- biome/structures/mood/raw_keywords는 모두 **한국어**로 작성합니다.
- biome: 지형/환경 (예: 숲, 바다, 사막, 설원, 동굴, 산악, 초원, 강)
- structures: 인공 구조물 (예: 마을, 성, 신전, 던전, 상점, 항구, 빌딩, 사무실)
- mood: 분위기 형용사 (예: 평화로운, 신비로운, 어두운, 웅장한, 아늑한)
- era: fantasy / medieval / modern / sf / mixed 중 하나.
- scale: small / medium / large / world 중 하나.
- tileset_hint: 다음 매핑으로 era와 era에 맞는 타일셋 ID 리스트를 채웁니다.
    1 = 월드맵 (전 세계 지도)
    2 = 자연/야외 (숲·마을·사막·바다)
    3 = 건물 실내 (집·상점·여관)
    4 = 던전/지하 (동굴·미궁·성 내부)
    5 = 현대 야외 (도시 거리·공원)
    6 = SF/현대 실내 (사무실·연구소·우주선)
  예: 판타지 RPG → [1,2,3,4]   현대 도시 → [5,6]   SF → [5,6]
- n_maps: 사용자가 명시하지 않으면 3.
- raw_keywords: 쿼리에서 직접 뽑은 핵심 한국어 키워드 (biome/structures/mood와 중복 가능).

반드시 JSON 스키마를 정확히 따르세요."""


_FEW_SHOT_USER = "판타지 RPG 게임을 만들어줘. 마을과 던전이 있으면 좋겠어."
_FEW_SHOT_ASSISTANT_HINT = """예시 의도:
- biome: ["숲","평원"]
- structures: ["마을","던전"]
- mood: ["모험적인"]
- era: "fantasy"
- scale: "medium"
- tileset_hint: [1,2,3,4]
- n_maps: 3
- raw_keywords: ["판타지","RPG","마을","던전"]"""


async def extract_intent(query: str, *, n_maps: int | None = None) -> MapIntent:
    """쿼리를 MapIntent로 변환한다.

    Args:
        query: 사용자 자연어 쿼리.
        n_maps: 명시적으로 맵 개수를 강제할 때 사용 (selector에서 호출 시).
    """
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=f"참고 예시:\n사용자: {_FEW_SHOT_USER}\n{_FEW_SHOT_ASSISTANT_HINT}"),
        HumanMessage(content=f"이제 다음 쿼리를 변환하세요:\n{query}"),
    ]

    try:
        result = await invoke_llm(messages, structured_output=MapIntent, temperature=0.0)
        intent = cast(MapIntent, result)
    except Exception:
        logger.exception("MapIntent 추출 실패, fallback intent 사용")
        intent = MapIntent(raw_keywords=[query])

    if n_maps is not None:
        intent.n_maps = n_maps
    return intent
