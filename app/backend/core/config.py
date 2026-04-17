"""
Configuration Settings
환경 변수를 관리하는 설정 파일

APP_ENV 환경변수에 따라 .env.development 또는 .env.production을 자동 선택한다.
배포 시(EC2 Docker) GitHub Actions의 ENV_FILE 시크릿으로 .env.production이 생성되며,
로컬은 .env.development 또는 기본값을 사용합니다.
"""

import json
import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values, load_dotenv
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _resolve_env_file() -> str:
    """APP_ENV 값에 따라 .env.development 또는 .env.production 경로를 반환한다."""
    raw = (os.getenv("APP_ENV") or "development").lower().strip()
    env_name = "production" if raw in ("prod", "production") else "development"
    candidate = _PROJECT_ROOT / f".env.{env_name}"
    return str(candidate if candidate.exists() else _PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    """애플리케이션 설정"""

    model_config = SettingsConfigDict(
        env_file=_resolve_env_file(),
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

    # ── 관리자 ──────────────────────────────────────────────
    ADMIN_EMAIL: str = ""  # 해당 이메일로 가입하면 자동 관리자

    # ── 알림 (선택) ─────────────────────────────────────────
    # 비어 있으면 전역 예외 시 Discord 로 전송하지 않음
    DISCORD_WEBHOOK_URL: str = ""
    # 비어 있으면 LLM 토큰/비용 요약을 Discord 로 보내지 않음 (에러 알림과 채널 분리 권장)
    DISCORD_TOKEN_WEBHOOK_URL: str = ""
    # 토큰/비용 Discord 알림 임계값 (0 = 해당 조건 미사용). 둘 다 0이면 기존처럼 토큰만 있으면 전송.
    # 둘 다 0보다 크면: (합계 토큰 >= MIN_TOTAL) 또는 (비용 >= MIN_COST) 일 때만 전송.
    DISCORD_TOKEN_ALERT_MIN_TOTAL_TOKENS: int = 0
    DISCORD_TOKEN_ALERT_MIN_COST_USD: float = 0.0

    @model_validator(mode="after")
    def _fill_discord_webhook_from_environ(self):
        """import 순서·파서 차이로 비는 경우를 위해 os.environ에서 한 번 더 보강."""
        if (self.DISCORD_WEBHOOK_URL or "").strip():
            return self
        v = (os.getenv("DISCORD_WEBHOOK_URL") or os.getenv("discord_webhook_url") or "").strip()
        if v:
            self.DISCORD_WEBHOOK_URL = v
        return self

    @model_validator(mode="after")
    def _fill_discord_token_webhook_from_environ(self):
        if (self.DISCORD_TOKEN_WEBHOOK_URL or "").strip():
            return self
        v = (
            os.getenv("DISCORD_TOKEN_WEBHOOK_URL") or os.getenv("discord_token_webhook_url") or ""
        ).strip()
        if v:
            self.DISCORD_TOKEN_WEBHOOK_URL = v
        return self

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


def loaded_env_file_path() -> str:
    """`Settings`가 `env_file`로 읽는 경로(로그·디버깅용). APP_ENV와 파일 존재 여부에 따라 달라짐."""
    return _resolve_env_file()


# agent.core.config는 `.env.{환경}`(또는 `.env`)만 로드한다.
# DISCORD 등 공통 비밀을 루트 `.env`에만 두는 경우가 많으므로, 먼저 루트를 넣고
# 환경별 파일로 덮어쓴다(환경 파일에 없는 키는 루트에서 온 값이 유지됨).
_root_env = _PROJECT_ROOT / ".env"
if _root_env.exists():
    load_dotenv(_root_env, override=False)
load_dotenv(_resolve_env_file(), override=True)

# 전역 설정 인스턴스
settings = Settings()

# `.env.development` 등에 `DISCORD_WEBHOOK_URL=` 빈 줄만 있으면 load_dotenv가 루트 `.env` 값을 지워
# 버릴 수 있음. Settings 직후에도 비면 루트 파일을 직접 파싱해 한 번 더 복구한다.
if not (settings.DISCORD_WEBHOOK_URL or "").strip() and _root_env.is_file():
    _dv = (dotenv_values(_root_env).get("DISCORD_WEBHOOK_URL") or "").strip()
    if _dv:
        settings.DISCORD_WEBHOOK_URL = _dv
        os.environ["DISCORD_WEBHOOK_URL"] = _dv

if not (settings.DISCORD_TOKEN_WEBHOOK_URL or "").strip() and _root_env.is_file():
    _dv_t = (dotenv_values(_root_env).get("DISCORD_TOKEN_WEBHOOK_URL") or "").strip()
    if _dv_t:
        settings.DISCORD_TOKEN_WEBHOOK_URL = _dv_t
        os.environ["DISCORD_TOKEN_WEBHOOK_URL"] = _dv_t
