import logging
import os

from agent.rag.embeddings import upstage_embeddings
from agent.rag.vectorstore import vector_store

logger = logging.getLogger(__name__)


class KnowledgeRetriever:
    """RPG Maker MZ 기술 지식 검색기 (SQLite3 기반)"""

    def __init__(self, collection_name: str = "knowledge"):
        self.collection_name = collection_name
        self.source_files = [
            "agent/rag/data/rpgmaker-mz-data-schema.md",
            "agent/rag/data/rpgmaker-mz-data-schema2.md",
        ]

    def index_markdown_file(self, file_path: str, force: bool = False):
        """지식 파일을 인덱싱 (섹션 단위 분할 및 벡터화)"""
        if not os.path.exists(file_path):
            print(f"  [Knowledge] 파일 없음: {file_path}")
            return

        # 중복 인덱싱 방지 (force=True인 경우 제외)
        try:
            if (
                not force
                and vector_store.count(
                    self.collection_name, where={"source_file": os.path.basename(file_path)}
                )
                > 0
            ):
                print(
                    f"  [Knowledge] '{os.path.basename(file_path)}' 지식이 이미 존재합니다. 건너뜁니다."
                )
                return
        except Exception:
            pass

        print(f"  [Knowledge] 인덱싱 시작: {file_path}")
        with open(file_path, encoding="utf-8") as f:
            content = f.read()

        # 섹션 단위 분할 (## 또는 #)
        sections = content.split("\n## ")
        if len(sections) <= 1:
            sections = content.split("\n# ")

        texts, metadatas, ids = [], [], []
        file_name = os.path.basename(file_path)

        for i, section in enumerate(sections):
            text = section.strip()
            if not text:
                continue

            header = text.split("\n")[0].strip()
            # 메타데이터에 출처 파일 명시 (LLM 판단 도구)
            texts.append(text)
            metadatas.append({"source_file": file_name, "header": header, "category": "Knowledge"})
            # 고유 ID 생성 (파일명 + 인덱스)
            ids.append(f"{file_name}_{i}")

        if texts:
            print(f"  [Knowledge] {file_name}에서 {len(texts)}개 섹션 임베딩 중...")
            vectors = upstage_embeddings.embed_documents(texts)
            vector_store.add_documents(self.collection_name, ids, vectors, texts, metadatas)
            print(f"  [Knowledge] {file_name} 저장 완료!")

    def reindex_all(self):
        """모든 지식 파일을 다시 인덱싱 (기존 데이터 삭제 후 갱신)"""
        print("\n[Knowledge] 전체 지식 DB 재인덱싱 시작...")
        # 기존 컬렉션 데이터 삭제 (필요 시 vector_store에 삭제 기능 추가 권장)
        # 현재는 동일한 ID로 덮어씌워지거나 수동으로 db 파일 삭제 후 실행 권장
        for file in self.source_files:
            self.index_markdown_file(file, force=True)
        print("[Knowledge] 전체 재인덱싱 완료!\n")

    def retrieve_knowledge(self, query: str, k: int = 3) -> str:
        """가장 관련성 높은 기술 지식 검색 (여러 파일 통합 결과 반환)"""
        try:
            # 데이터가 하나도 없으면 자동 인덱싱
            if vector_store.count(self.collection_name) == 0:
                print("  [Knowledge] DB가 비어있습니다. 초기 인덱싱을 시작합니다.")
                self.reindex_all()
        except Exception:
            self.reindex_all()

        print(f"  [Knowledge] 통합 지식 검색 중: '{query}'")
        try:
            query_vector = upstage_embeddings.embed_query(query)
            results = vector_store.similarity_search(
                self.collection_name, query_vector, k=k, where={"category": "Knowledge"}
            )

            if results and results.get("documents") and results["documents"][0]:
                formatted_results = []
                for i, doc in enumerate(results["documents"][0]):
                    source = results["metadatas"][0][i].get("source_file", "Unknown")
                    formatted_results.append(f"### [지식 출처: {source}]\n{doc}")

                return "\n\n---\n\n".join(formatted_results)
        except Exception as e:
            print(f"  [Knowledge] 검색 중 오류: {e}")

        return "관련된 기술 지식을 찾지 못했습니다."


knowledge_retriever = KnowledgeRetriever()
