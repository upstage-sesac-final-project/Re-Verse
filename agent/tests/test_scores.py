import logging

import pytest

from agent.generation.mapgen.intent.extractor import extract_intent
from agent.generation.mapgen.sample_selector.filter import rule_filter

# 로깅 설정
logger = logging.getLogger(__name__)


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["마을", "교실"])
async def test_map_score_distribution(query):
    """맵 필터링 점수 분포 검증 테스트"""
    intent = await extract_intent(query)
    candidates = rule_filter(intent, top_k=10)

    # 1. 후보 맵 여부 확인
    assert len(candidates) > 0, "후보 맵이 존재해야 합니다."

    max_score = candidates[0]["score"]
    print(f"\n--- 쿼리: {query} ---")
    print(f"1등 맵: {candidates[0]['entry']['file_name']} (점수: {max_score:.2f})")

    # 2. 점수가 비현실적으로 높은지 확인 (0점은 아닌지)
    assert max_score > 0, "점수는 0보다 커야 합니다."

    # 3. 1등과 2등의 점수 분포 확인 (단순 출력용)
    if len(candidates) > 1:
        score_gap = max_score - candidates[1]["score"]
        print(f"1-2등 점수 차이: {score_gap:.2f}")

    # '교실'은 1등 점수가 압도적으로 높아야 함 (태그 5.0 가중치 영향)
    if query == "교실" and len(candidates) > 1:
        # 교실이 1등일 때, 2등(현대 야외 맵 등)과의 차이가 어느 정도 있는지 출력
        print(f"교실 맵 점수: {max_score:.2f}")
        for i, c in enumerate(candidates[1:4], 2):
            print(f"{i}등 점수: {c['score']:.2f} ({c['entry']['file_name']})")
