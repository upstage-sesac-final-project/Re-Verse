"""
Configuration Settings
환경 변수를 관리하는 설정 파일
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """애플리케이션 설정"""

    # App Settings
    ENVIRONMENT: str = "development"  # 로컬: development, 배포: production
    DEBUG: bool = True  # 로컬: True, 배포: False

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",  # 로컬 프론트엔드
        "https://*.vercel.app",  # Vercel 배포된 프론트엔드
    ]

    # Upstage API
    UPSTAGE_API_KEY: str = ""
    SOLAR_API_BASE_URL: str = "https://api.upstage.ai/v1/solar"
    SOLAR_MODEL: str = "solar-pro"

    # LangSmith
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "Re-Verse_project"
    LANGSMITH_TRACING: bool = True

    # Storage
    STORAGE_PATH: str = "./storage/games"

    # Agent Settings
    AGENT_TIMEOUT: int = 30  # seconds
    MAX_RETRIES: int = 3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True


# 전역 설정 인스턴스
settings = Settings()
