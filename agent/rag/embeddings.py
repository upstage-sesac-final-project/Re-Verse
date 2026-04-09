from langchain_upstage import UpstageEmbeddings

from agent.core.config import agent_config


class RPGEmbeddings:
    """Upstage 공식 라이브러리를 이용한 임베딩 클래스 (AgentConfig 통합)"""

    def __init__(self):
        if not agent_config.LLM_API_KEY:
            raise ValueError("LLM_API_KEY가 설정되어 있지 않습니다. .env 파일을 확인하세요.")

        # 쿼리 전용 임베딩 모델
        self.query_model = UpstageEmbeddings(
            api_key=agent_config.LLM_API_KEY, model="solar-embedding-1-large-query"
        )
        # 문장 전용 임베딩 모델
        self.passage_model = UpstageEmbeddings(
            api_key=agent_config.LLM_API_KEY, model="solar-embedding-1-large-passage"
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """문서 리스트를 임베딩 벡터로 변환 (Passage 모델)"""
        return self.passage_model.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        """쿼리 문자열을 임베딩 벡터로 변환 (Query 모델)"""
        return self.query_model.embed_query(text)


# 싱글톤 — lazy 초기화 (import 시점에 API 키 없어도 에러 안 남)
_instance: RPGEmbeddings | None = None


def get_embeddings() -> RPGEmbeddings:
    """최초 호출 시 RPGEmbeddings 인스턴스 생성. API 키 없으면 이 시점에 에러."""
    global _instance
    if _instance is None:
        _instance = RPGEmbeddings()
    return _instance


# 하위호환: 기존 코드에서 upstage_embeddings 직접 참조하는 곳 대응
class _LazyProxy:
    """속성 접근 시점에 실제 인스턴스 생성."""

    def __getattr__(self, name: str):
        return getattr(get_embeddings(), name)


upstage_embeddings = _LazyProxy()
