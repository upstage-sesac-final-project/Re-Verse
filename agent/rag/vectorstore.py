import json
import math
import os
import sqlite3
from typing import Any


class SQLiteVectorStore:
    """SQLite3 기반의 안정적인 영구 저장 벡터 저장소"""

    def __init__(self, db_path: str = "storage/vector_store.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """DB 테이블 초기화"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    collection_name TEXT,
                    vector TEXT,
                    content TEXT,
                    metadata TEXT
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_collection ON documents(collection_name)"
            )
            conn.commit()

    def count(self, collection_name: str, where: dict[str, Any] | None = None) -> int:
        """특정 컬렉션(및 필터)의 데이터 개수 조회"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if not where:
                cursor.execute(
                    "SELECT COUNT(*) FROM documents WHERE collection_name = ?", (collection_name,)
                )
                return cursor.fetchone()[0]

            # 간단한 필터링 쿼리 생성 (category, game_id 등)
            query = "SELECT COUNT(*) FROM documents WHERE collection_name = ?"
            params = [collection_name]
            for key, val in where.items():
                query += f" AND json_extract(metadata, '$.{key}') = ?"
                params.append(val)

            cursor.execute(query, tuple(params))
            return cursor.fetchone()[0]

    def add_documents(
        self,
        collection_name: str,
        ids: list[str],
        vectors: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ):
        """문서 추가"""
        print(f"    [VectorStore] '{collection_name}'에 {len(ids)}개 데이터 저장 중...")
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for id_, vec, doc, meta in zip(ids, vectors, documents, metadatas):
                cursor.execute(
                    "INSERT OR REPLACE INTO documents (id, collection_name, vector, content, metadata) VALUES (?, ?, ?, ?, ?)",
                    (id_, collection_name, json.dumps(vec), doc, json.dumps(meta)),
                )
            conn.commit()
        print("    [VectorStore] 저장 완료!")

    def _cosine_similarity(self, v1: list[float], v2: list[float]) -> float:
        dot_product = sum(x * y for x, y in zip(v1, v2))
        norm1 = math.sqrt(sum(x * x for x in v1))
        norm2 = math.sqrt(sum(y * y for y in v2))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def similarity_search(
        self,
        collection_name: str,
        query_vector: list[float],
        k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """유사도 검색"""
        all_docs = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # 메타데이터 필터링 (간단히 처리)
            cursor.execute(
                "SELECT id, vector, content, metadata FROM documents WHERE collection_name = ?",
                (collection_name,),
            )
            rows = cursor.fetchall()

            for row in rows:
                doc_id, vec_json, content, meta_json = row
                vec = json.loads(vec_json)
                meta = json.loads(meta_json)

                # 'where' 필터링 로직 (category 등)
                if where:
                    match = True
                    for key, val in where.items():
                        if meta.get(key) != val:
                            match = False
                            break
                    if not match:
                        continue

                score = self._cosine_similarity(query_vector, vec)
                all_docs.append(
                    {"id": doc_id, "document": content, "metadata": meta, "score": score}
                )

        # 점수 순 정렬
        all_docs.sort(key=lambda x: x["score"], reverse=True)
        top_k = all_docs[:k]

        # ChromaDB 호환 형식으로 변환하여 반환
        return {
            "ids": [[d["id"] for d in top_k]],
            "documents": [[d["document"] for d in top_k]],
            "metadatas": [[d["metadata"] for d in top_k]],
            "distances": [[1.0 - d["score"] for d in top_k]],
        }


# 싱글톤 인스턴스
vector_store = SQLiteVectorStore()
