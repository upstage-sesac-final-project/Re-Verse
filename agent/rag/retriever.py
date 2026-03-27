import json
import os
from typing import Any

from agent.rag.embeddings import upstage_embeddings
from agent.rag.vectorstore import vector_store


class RPGRetriever:
    """SQLite3 기반 벡터 저장소를 사용하는 게임 데이터 검색기"""

    def __init__(self, game_id: str, collection_name: str = "game_data"):
        self.game_id = game_id
        self.collection_name = collection_name
        self.data_dir = os.path.join("storage", "games", game_id, "data")

    def index_category(self, category: str):
        """특정 카테고리(Actors 등) 인덱싱 확인 및 수행"""
        # 해당 카테고리 데이터가 이미 있는지 효율적으로 확인
        try:
            count = vector_store.count(
                self.collection_name, where={"category": category, "game_id": self.game_id}
            )
            if count > 0:
                # print(f"  [RAG] {category} 데이터가 이미 존재합니다. ({count}건)")
                return  # 이미 존재
        except Exception as e:
            print(f"  [RAG] 체크 중 오류 (진행): {e}")

        filename = f"{category}.json"
        file_path = os.path.join(self.data_dir, filename)
        if not os.path.exists(file_path):
            return

        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        texts, metadatas, ids = [], [], []
        for item in data:
            if item is None or "name" not in item:
                continue
            name = item.get("name", "")
            desc = item.get("description", "")
            texts.append(f"[{category}] 이름: {name}, 설명: {desc}")
            metadatas.append(
                {
                    "id": str(item.get("id")),
                    "name": name,
                    "category": category,
                    "game_id": self.game_id,
                }
            )
            ids.append(f"{self.game_id}_{category}_{item.get('id')}")

        if texts:
            print(f"  [RAG] {category} 데이터 임베딩 및 SQLite 저장 중...")
            vectors = upstage_embeddings.embed_documents(texts)
            vector_store.add_documents(self.collection_name, ids, vectors, texts, metadatas)

    def retrieve_entities(self, query: str, category: str, k: int = 3) -> list[dict[str, Any]]:
        """특정 카테고리 내에서 엔티티 검색"""
        self.index_category(category)

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
