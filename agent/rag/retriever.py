import hashlib
import json
import logging
from typing import Any

from agent.rag.embeddings import upstage_embeddings
from agent.rag.vectorstore import vector_store
from agent.utils.game_data_io import get_game_data_dir, read_game_json

logger = logging.getLogger(__name__)


class RPGRetriever:
    """SQLite3 기반 벡터 저장소를 사용하는 게임 데이터 검색기"""

    def __init__(self, game_id: str, collection_name: str = "game_data"):
        self.game_id = game_id
        self.collection_name = collection_name
        self.data_dir = get_game_data_dir(game_id)

    def _get_data_hash(self, data: Any) -> str:
        """데이터의 MD5 해시값을 계산한다. (중복 인덱싱 방지용)"""
        # 정렬된 키를 사용하여 일관된 해시 생성
        content = json.dumps(data, sort_keys=True, ensure_ascii=False)
        return hashlib.md5(content.encode("utf-8")).hexdigest()

    async def index_category(self, category: str, force: bool = False):
        """특정 카테고리(Actors 등) 인덱싱 확인 및 수행.
        데이터가 변경된 경우(해시 불일치) 자동으로 재인덱싱한다.
        """
        data = read_game_json(self.game_id, category)
        if not data:
            return

        # 유효한 아이템(이름이 있는 것)만 필터링
        valid_items = [item for item in data if item and "name" in item]
        if not valid_items:
            return

        current_hash = self._get_data_hash(valid_items)

        # 1. 기존 데이터의 해시값 확인 (메타데이터 활용)
        if not force:
            try:
                # 해당 카테고리의 데이터 1건을 조회하여 해시 비교
                existing = vector_store.search_by_metadata(
                    self.collection_name,
                    where={"category": category, "game_id": self.game_id},
                    limit=1,
                )
                if existing and existing[0].get("metadata", {}).get("file_hash") == current_hash:
                    return  # 변경 사항 없음
            except Exception:
                pass

        # 2. 데이터가 변경되었거나 강제 업데이트인 경우 재인덱싱
        print(f"  [RAG] {category} 데이터 업데이트 감지. 인덱싱 갱신 중...")

        try:
            # 기존 카테고리 데이터 삭제
            vector_store.delete(
                self.collection_name, where={"category": category, "game_id": self.game_id}
            )
        except Exception as e:
            logger.error(f"Error deleting old index: {e}")

        texts, metadatas, ids = [], [], []
        for item in valid_items:
            name = item.get("name", "")
            desc = item.get("description", "")
            texts.append(f"[{category}] 이름: {name}, 설명: {desc}")
            metadatas.append(
                {
                    "id": str(item.get("id")),
                    "name": name,
                    "category": category,
                    "game_id": self.game_id,
                    "file_hash": current_hash,
                }
            )
            ids.append(f"{self.game_id}_{category}_{item.get('id')}")

        if texts:
            # CPU/IO 집약적인 작업이므로 비동기로 실행되도록 보장 (필요 시)
            vectors = upstage_embeddings.embed_documents(texts)
            vector_store.add_documents(self.collection_name, ids, vectors, texts, metadatas)

    async def update_indices(self, categories: list[str]):
        """수정된 파일 목록을 받아 선제적으로 인덱싱을 업데이트한다."""
        for cat in categories:
            # 파일명(.json) 또는 카테고리명 대응
            clean_cat = cat.replace(".json", "")
            await self.index_category(clean_cat)

    async def retrieve_entities(
        self, query: str, category: str, k: int = 3
    ) -> list[dict[str, Any]]:
        """특정 카테고리 내에서 엔티티 검색 (실행 전 자동 인덱싱 체크 포함)"""
        # 검색 전 인덱스가 최신인지 확인 (해시 체크)
        await self.index_category(category)

        query_vector = upstage_embeddings.embed_query(query)
        results = vector_store.similarity_search(
            self.collection_name,
            query_vector,
            k=k,
            where={"category": category, "game_id": self.game_id},
        )

        formatted_results = []
        if results and results.get("metadatas"):
            for i in range(len(results["metadatas"][0])):
                meta = results["metadatas"][0][i]
                formatted_results.append(
                    {
                        "id": meta["id"],
                        "name": meta["name"],
                        "score": results["distances"][0][i] if results.get("distances") else 0,
                    }
                )
        return formatted_results
