"""Agent 레이어 설정 — 루트 .env에서 설정을 읽는다."""

from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 루트 .env 경로 (어느 디렉토리에서 실행해도 동일하게 참조)
_ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"

# 환경 변수를 os.environ에 로드 (MCP_ENABLED 등 직접 os.environ 접근용)
load_dotenv(_ROOT_ENV)


class AgentConfig(BaseSettings):
    """LLM 및 에이전트 동작 설정.

    Solar, OpenAI, vLLM 등 OpenAI 호환 API를 모두 지원한다.
    프로바이더 전환은 .env 의 LLM_BASE_URL 과 LLM_MODEL 만 바꾸면 된다.

    Solar  예시: LLM_BASE_URL=https://api.upstage.ai/v1  LLM_MODEL=solar-pro
    OpenAI 예시: LLM_BASE_URL=  (비움)                   LLM_MODEL=gpt-4o
    vLLM   예시: LLM_BASE_URL=http://localhost:8001/v1   LLM_MODEL=Llama-3.1-8B
    """

    # ── LLM ─────────────────────────────────────────────────
    LLM_API_KEY: str = ""
    LLM_MODEL: str = "solar-pro3"
    LLM_BASE_URL: str = "https://api.upstage.ai/v1"  # 비우면 공식 OpenAI

    # ── 공통 LLM 파라미터 ────────────────────────────────────
    LLM_MAX_TOKENS: int = 4096
    LLM_TEMPERATURE: float = 0.0  # 에이전트는 결정론적 출력이 기본
    LLM_PARALLEL_TOOL_CALLS: bool = False  # Solar API 호환성을 위해 기본값 False

    # ── LangSmith ────────────────────────────────────────────
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "Re-Verse"
    LANGSMITH_TRACING: bool = False  # True 로 바꾸면 모든 LLM 호출이 트레이싱됨

    # ── 에이전트 동작 ────────────────────────────────────────
    AGENT_TIMEOUT: int = 30
    LLM_TIMEOUT: int = 300  # 단일 LLM ainvoke 최대 대기 시간(초)
    MAX_RETRIES: int = 3

    # ── 대화 이력 ────────────────────────────────────────────
    HISTORY_WINDOW_SIZE: int = 10  # 최근 N턴 그대로 전달
    HISTORY_SUMMARY_WINDOW: int = 10  # 그 이전 N턴 요약 압축

    model_config = {
        "env_file": str(_ROOT_ENV),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


# 싱글톤
agent_config = AgentConfig()
