"""샘플맵 선택기 entrypoint.

쿼리 → MapIntent → 룰 필터 → LLM 재랭킹 → file_name 리스트.

CLI 사용:
    uv run python -m agent.generation.mapgen.sample_selector.selector "판타지 게임 만들어줘"
"""

import argparse
import asyncio
import logging

from agent.generation.mapgen.intent.extractor import extract_intent
from agent.generation.mapgen.sample_selector.filter import DEFAULT_TOP_K, load_metadata, rule_filter

logger = logging.getLogger(__name__)


async def select_maps(
    query: str,
    *,
    n_maps: int = 3,
    top_k: int = DEFAULT_TOP_K,
) -> dict[str, list]:
    """쿼리에 가장 어울리는 샘플맵 세트(연결된 체인)를 반환."""
    intent = await extract_intent(query, n_maps=n_maps)

    # 1. 후보군 추출
    candidates = rule_filter(intent, top_k=top_k)
    metadata = load_metadata()
    metadata_map = {m["file_name"]: m for m in metadata}
    id_to_file = {
        int(m["file_name"].replace("Map", "").replace(".json", "")): m["file_name"]
        for m in metadata
    }

    # 2. 첫 번째 'Seed' 맵 선정 (가장 점수 높은 놈)
    if not candidates:
        return {"chosen": [], "candidates": []}

    seed_file = candidates[0]["entry"]["file_name"]
    chosen = [seed_file]

    # 3. 연결된 맵 추적 (Chain Selection)
    current_file = seed_file
    for _ in range(n_maps - 1):
        meta = metadata_map.get(current_file)
        if not meta or "exits" not in meta:
            break

        # 출구들 중에서 다음 맵 후보 찾기
        next_candidates = []
        for ex in meta["exits"]:
            target_id = ex.get("leads_to_id")
            if target_id and target_id in id_to_file:
                target_file = id_to_file[target_id]
                if target_file not in chosen:
                    next_candidates.append(target_file)

        if next_candidates:
            # 연결된 것 중 테마 점수가 가장 높은 것 선택 (간략화: 첫 번째 후보)
            # TODO: 여기서도 rule_filter 점수를 참고하면 더 좋음
            current_file = next_candidates[0]
            chosen.append(current_file)
        else:
            # 연결이 끊기면 다시 룰 필터에서 보충
            for cand in candidates:
                fn = cand["entry"]["file_name"]
                if fn not in chosen:
                    chosen.append(fn)
                    current_file = fn
                    break

    logger.info("연결성 기반 맵 선택 완료: %s", " -> ".join(chosen))
    return {"chosen": chosen[:n_maps], "candidates": candidates}


async def _amain() -> None:
    parser = argparse.ArgumentParser(description="샘플맵 선택기")
    parser.add_argument("query", help="자연어 게임 생성 쿼리")
    parser.add_argument("-n", "--n-maps", type=int, default=3, help="선택할 맵 개수 (1~10)")
    parser.add_argument("-k", "--top-k", type=int, default=DEFAULT_TOP_K, help="룰 필터 후보 수")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    result = await select_maps(args.query, n_maps=args.n_maps, top_k=args.top_k)
    chosen = result["chosen"]
    print("\n선택된 맵:")
    for i, fn in enumerate(chosen, 1):
        print(f"  {i}. {fn}")


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
