import logging

import pytest

from agent.generation.mapgen.intent.extractor import extract_intent
from agent.generation.mapgen.sample_selector.filter import rule_filter

# 로깅 설정 (pytest -s로 실행 시 출력 확인 가능)
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["마을", "교실", "사막 던전"])
async def test_intent_extraction_logic(query):
    """의도 추출 및 후보 맵 필터링 로직 검증 테스트"""
    intent = await extract_intent(query)
    all_kws = intent.all_keywords()

    print(f"\n--- 쿼리: {query} ---")
    print(f"추출된 키워드: {all_kws}")
    print(f"타일셋 힌트: {intent.tileset_hint}")

    # 1. 키워드 추출 확인
    assert len(all_kws) > 0, f"'{query}'에 대해 키워드가 추출되지 않았습니다."

    # 2. 타일셋 힌트 확인
    assert len(intent.tileset_hint) > 0, f"'{query}'에 대해 타일셋 힌트가 추출되지 않았습니다."

    # 3. 필터링 결과 확인
    candidates = rule_filter(intent, top_k=5)
    assert len(candidates) > 0, "후보 맵이 검색되지 않았습니다."

    print(f"1등 후보: {candidates[0]['entry']['display_name']} ({candidates[0]['score']:.2f})")

    # 교실 쿼리일 경우 특정 결과 검증
    if "교실" in query:
        # 교실이 1등이거나 최소한 상위권에 있어야 함
        top_files = [c["entry"]["file_name"] for c in candidates]
        assert "Map091.json" in top_files, "교실 맵(Map091)이 상위권에 포함되지 않았습니다."
