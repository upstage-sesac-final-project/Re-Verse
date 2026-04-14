"""Agent 레이어 설정 — APP_ENV에 따라 .env.{환경} 파일을 읽는다."""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_env_file() -> Path:
    """APP_ENV 값에 따라 .env.development 또는 .env.production 경로를 반환한다."""
    raw = (os.getenv("APP_ENV") or "development").lower().strip()
    env_name = "production" if raw in ("prod", "production") else "development"
    candidate = _PROJECT_ROOT / f".env.{env_name}"
    return candidate if candidate.exists() else _PROJECT_ROOT / ".env"


_ROOT_ENV = _resolve_env_file()

# 환경 변수를 os.environ에 로드 (MCP_ENABLED 등 직접 os.environ 접근용)
# 루트 `.env`에만 둔 공통 키가 `.env.development` 등에 없어도 유지되도록 먼저 로드한다.
_root_dotenv = _PROJECT_ROOT / ".env"
if _root_dotenv.exists():
    load_dotenv(_root_dotenv, override=False)
load_dotenv(_ROOT_ENV, override=True)


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
        "env_file": str(_resolve_env_file()),
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


# 싱글톤
agent_config = AgentConfig()
