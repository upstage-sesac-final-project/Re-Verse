"""
Configuration Settings
환경 변수를 관리하는 설정 파일

배포 시(EC2 Docker) GitHub Actions의 ENV_FILE 시크릿으로 .env가 생성되며,
로컬은 .env 또는 기본값을 사용합니다.
"""

import json
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App Settings
    ENVIRONMENT: str = "development"  # development | production
    DEBUG: bool = True

    # ── CORS (프론트: Vercel https://re-verse.ai.kr 등) ─────────────────
    # 쉼표로 구분. FastAPI는 와일드카드 origin을 신뢰하지 않으므로 도메인을 명시합니다.
    CORS_ORIGINS: str = Field(
        default=(
            "http://localhost:5173,http://localhost:3000,"
            "https://re-verse.ai.kr,https://www.re-verse.ai.kr"
        ),
        description="허용 Origin 목록 (쉼표 구분)",
    )

    # ── 게임 파일 저장 ────────────────────────────────────────────────
    # 로컬 개발: ./storage/games (그대로 파일 수정)
    # 프로덕션: EC2 컨테이너 내 경로 + S3 동기화(STORAGE_BACKEND=s3)
    STORAGE_PATH: str = "./storage/games"

    # local: 디스크만 사용 | s3: 요청 시 S3에서 받아 수정 후 다시 업로드
    STORAGE_BACKEND: Literal["local", "s3"] = "local"

    # AWS S3 (EC2 IAM 역할 사용 시 ACCESS_KEY 불필요)
    AWS_REGION: str = "ap-northeast-2"
    S3_BUCKET_NAME: str = "upstage-sesac-31-reverse-project-s3"
    # 버킷 내 게임 루트 prefix (키 예: games/game_001/data/Actors.json)
    S3_PREFIX: str = "games"

    # RDS PostgreSQL (비어 있으면 DB 엔진 미생성, 헬스는 skipped)
    # 예: postgresql+psycopg://user:pass@host:5432/dbname?sslmode=require
    DATABASE_URL: str = ""

    # ── JWT ─────────────────────────────────────────────────
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRATION_HOURS: int = 24

    # ── 프로젝트 ──────────────────────────────────────────────
    BASE_GAME_PATH: str = "./storage/games/base_game"
    MAX_PROJECTS_PER_USER: int = 3

    @field_validator("JWT_SECRET_KEY", mode="after")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        """JWT_SECRET_KEY가 비어 있으면 시작 차단."""
        if not v:
            raise ValueError("JWT_SECRET_KEY must be set in .env")
        return v

    @field_validator("S3_PREFIX", mode="before")
    @classmethod
    def normalize_s3_prefix(cls, v: str) -> str:
        """앞뒤 슬래시 제거 — 키 조합 시 일관되게 붙임."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return "games"
        return str(v).strip().strip("/")

    def cors_origins_list(self) -> list[str]:
        """CORSMiddleware용 리스트.

        `.env`에서 쉼표 구분 또는 JSON 배열(`["http://a","https://b"]`) 둘 다 허용.
        """
        raw = self.CORS_ORIGINS.strip()
        if raw.startswith("["):
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return [str(x).strip() for x in data if str(x).strip()]
            except json.JSONDecodeError:
                pass
        return [x.strip() for x in raw.split(",") if x.strip()]


# 전역 설정 인스턴스
settings = Settings()
