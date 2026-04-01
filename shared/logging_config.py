"""중앙 집중식 로깅 설정 — backend·agent 공용.

backend(main.py lifespan)에서 setup_logging()을 한 번 호출하면
모든 모듈(agent.*, app.backend.*, shared.*)의 로거에 설정이 적용된다.
agent 단독 테스트 시에도 직접 import하여 호출 가능.

환경변수:
    LOG_LEVEL              : DEBUG | INFO | WARNING | ERROR (미설정 시 자동 결정)
    LOG_DIR                : 로그 파일 저장 경로 (기본: ./logs)
    LOG_LEVEL_SQLALCHEMY   : SQLAlchemy 로거 레벨 오버라이드 (기본: WARNING)
    LOG_LEVEL_HTTPX        : HTTPX 로거 레벨 오버라이드 (기본: WARNING)

상세 설정 문서: docs/backend/logging.md
"""

import json
import logging
import logging.config
import os
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv


class JsonFormatter(logging.Formatter):
    """프로덕션용 단일 라인 JSON 포매터.

    출력 예시:
        {"timestamp":"2026-04-02T01:02:21.038+00:00","level":"INFO","logger":"agent.graph.nodes.planner","message":"..."}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging() -> None:
    """앱 시작 시 한 번 호출하여 전체 로깅을 초기화한다."""

    # .env 파일에서 환경변수 로드 (os.getenv는 .env를 자동으로 읽지 않음)
    load_dotenv()

    log_level = os.getenv("LOG_LEVEL", "").upper()
    environment = os.getenv("ENVIRONMENT", "development")
    debug = os.getenv("DEBUG", "false").lower() in ("true", "1", "yes")
    log_dir = os.getenv("LOG_DIR", "./logs")

    # 유효 레벨 결정: LOG_LEVEL 직접 설정 > DEBUG=true면 DEBUG > 그 외 INFO
    if log_level and hasattr(logging, log_level):
        effective_level = log_level
    elif debug:
        effective_level = "DEBUG"
    else:
        effective_level = "INFO"

    is_production = environment == "production"

    # 로그 디렉토리 생성 (없으면 자동 생성)
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    # 개발: human-readable 포맷 / 프로덕션: JSON 포맷
    console_formatter = "json" if is_production else "readable"

    config: dict = {
        "version": 1,
        # True로 설정하면 dictConfig 호출 전에 생성된 로거가 비활성화됨
        # 각 모듈이 import 시점에 getLogger(__name__)로 로거를 생성하므로 반드시 False
        "disable_existing_loggers": False,
        "formatters": {
            # 개발용: 타임스탬프 | 레벨 | 로거명 | 메시지
            "readable": {
                "format": ("%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)s | %(message)s"),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            # 프로덕션용: JSON 한 줄 (로그 수집 시스템 파싱 용이)
            "json": {
                "()": JsonFormatter,
            },
        },
        "handlers": {
            # 콘솔 출력 (stderr)
            "console": {
                "class": "logging.StreamHandler",
                "formatter": console_formatter,
                "stream": "ext://sys.stderr",
            },
            # 파일 출력 (로테이션: 10MB 초과 시 백업, 최대 5개 = ~60MB)
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "json" if is_production else "readable",
                "filename": str(Path(log_dir) / "reverse.log"),
                "maxBytes": 10_485_760,  # 10 MB
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            # ── 프로젝트 로거: LOG_LEVEL 환경변수로 제어 ──
            "agent": {
                "level": effective_level,
                "handlers": ["console", "file"],
                "propagate": False,  # root 로거로 전파 방지 (중복 출력 방지)
            },
            "app.backend": {
                "level": effective_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "shared": {
                "level": effective_level,
                "handlers": ["console", "file"],
                "propagate": False,
            },
            # ── 서드파티 로거: 개별 환경변수로 오버라이드 가능 ──
            "sqlalchemy": {
                "level": os.getenv("LOG_LEVEL_SQLALCHEMY", "WARNING"),
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "httpx": {
                "level": os.getenv("LOG_LEVEL_HTTPX", "WARNING"),
                "handlers": ["console", "file"],
                "propagate": False,
            },
            # ── uvicorn: INFO 고정 (서버 시작/종료 이벤트) ──
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console", "file"],
                "propagate": False,
            },
        },
        # 미등록 로거의 안전망 (WARNING 이상만 출력)
        "root": {
            "level": "WARNING",
            "handlers": ["console", "file"],
        },
    }

    logging.config.dictConfig(config)

    logger = logging.getLogger("shared.logging_config")
    logger.info(
        "Logging initialized: level=%s, environment=%s, log_dir=%s",
        effective_level,
        environment,
        log_dir,
    )
