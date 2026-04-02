"""중앙 집중식 로깅 설정 — backend·agent 공용.

backend(main.py lifespan)에서 setup_logging()을 한 번 호출하면
모든 모듈(agent.*, app.backend.*, shared.*)의 로거에 설정이 적용된다.
agent 단독 테스트 시에도 직접 import하여 호출 가능.

환경변수:
    LOG_LEVEL              : DEBUG | INFO | WARNING | ERROR (미설정 시 자동 결정)
    LOG_DIR                : 로그 파일 저장 경로 (기본: ./logs)
    LOG_LEVEL_SQLALCHEMY   : SQLAlchemy 로거 레벨 오버라이드 (기본: WARNING)
    LOG_LEVEL_HTTPX        : HTTPX 로거 레벨 오버라이드 (기본: WARNING)

로그 폴더 구조:
    logs/
    ├── general/                              # 일반 로그 (모든 레벨, 72시간 보존)
    │   └── {YYYY-MM-DD}/
    │       └── {username}_{user_id}/
    │           └── general.log
    └── error/                                # ERROR/WARNING 전용 (±3분 컨텍스트)
        └── {YYYY-MM-DD}/
            └── {username}_{user_id}/
                └── {YYYY-MM-DD_HH-MM-SS}_{LEVEL}.log

상세 설정 문서: docs/backend/logging.md
"""

import collections
import json
import logging
import logging.config
import os
import shutil
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

from shared.log_context import current_user_label

# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class JsonFormatter(logging.Formatter):
    """프로덕션용 단일 라인 JSON 포매터.

    출력 예시:
        {"timestamp":"2026-04-02T01:02:21.038+00:00","level":"INFO","logger":"agent.graph.nodes.planner","user":"genie_1","message":"..."}
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "user": getattr(record, "user_label", "anonymous"),
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


class UserLabelFilter(logging.Filter):
    """LogRecord에 user_label 속성을 주입하는 필터."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "user_label"):
            try:
                record.user_label = current_user_label.get()
            except LookupError:
                record.user_label = "anonymous"
        return True


# ---------------------------------------------------------------------------
# Custom Handlers
# ---------------------------------------------------------------------------


class DailyUserFileHandler(logging.Handler):
    """날짜/유저별 폴더에 일반 로그를 저장하는 핸들러.

    경로: {base_dir}/general/{YYYY-MM-DD}/{user_label}/general.log
    retention_hours 이상 지난 날짜 폴더를 자동 삭제한다.
    """

    def __init__(
        self,
        base_dir: str,
        retention_hours: int = 72,
        cleanup_interval: int = 500,
    ):
        super().__init__()
        self.base_dir = Path(base_dir) / "general"
        self.retention_hours = retention_hours
        self._cleanup_interval = cleanup_interval
        self._file_handles: dict[str, logging.FileHandler] = {}
        self._lock = threading.Lock()
        self._emit_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            user_label = getattr(record, "user_label", "anonymous")
            date_str = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d")
            key = f"{date_str}/{user_label}"

            with self._lock:
                handler = self._get_or_create_handler(key, date_str, user_label)
                handler.emit(record)

                self._emit_count += 1
                if self._emit_count >= self._cleanup_interval:
                    self._emit_count = 0
                    self._cleanup_old_logs()
        except Exception:
            self.handleError(record)

    def _get_or_create_handler(
        self, key: str, date_str: str, user_label: str
    ) -> logging.FileHandler:
        if key not in self._file_handles:
            log_dir = self.base_dir / date_str / user_label
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(str(log_dir / "general.log"), encoding="utf-8")
            handler.setFormatter(self.formatter)
            self._file_handles[key] = handler
        return self._file_handles[key]

    def _cleanup_old_logs(self) -> None:
        """retention_hours 이상 지난 날짜 폴더 삭제."""
        cutoff = datetime.now() - timedelta(hours=self.retention_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d")

        if not self.base_dir.exists():
            return

        for date_dir in self.base_dir.iterdir():
            if date_dir.is_dir() and date_dir.name < cutoff_str:
                keys_to_remove = [
                    k for k in self._file_handles if k.startswith(date_dir.name + "/")
                ]
                for k in keys_to_remove:
                    self._file_handles[k].close()
                    del self._file_handles[k]
                shutil.rmtree(date_dir, ignore_errors=True)

    def close(self) -> None:
        with self._lock:
            for handler in self._file_handles.values():
                handler.close()
            self._file_handles.clear()
        super().close()


class ErrorContextHandler(logging.Handler):
    """WARNING/ERROR 발생 시 ±3분 컨텍스트를 파일로 저장하는 핸들러.

    동작 방식:
        1. 모든 로그를 링 버퍼에 보관 (최근 context_minutes * 2 분)
        2. WARNING 이상 레벨 발생 시 캡처 시작:
           - 과거 context_minutes 분의 로그를 버퍼에서 추출
           - 이후 context_minutes 분간 추가 로그 수집
        3. 캡처 윈도우 종료 시 파일로 저장
        4. 백그라운드 타이머가 flush_interval_sec 마다 완료된 캡처를 플러시

    경로: {base_dir}/error/{YYYY-MM-DD}/{user_label}/{YYYY-MM-DD_HH-MM-SS}_{LEVEL}.log
    """

    def __init__(
        self,
        base_dir: str,
        context_minutes: int = 3,
        flush_interval_sec: float = 30.0,
    ):
        super().__init__()
        self.base_dir = Path(base_dir) / "error"
        self.context_seconds = context_minutes * 60
        self._flush_interval = flush_interval_sec
        self._buffer: collections.deque[tuple[float, logging.LogRecord]] = collections.deque()
        self._active_captures: dict[str, dict] = {}
        self._lock = threading.Lock()

        # 백그라운드 플러시 타이머
        self._shutdown = threading.Event()
        self._timer_thread = threading.Thread(
            target=self._flush_loop, daemon=True, name="ErrorContextFlusher"
        )
        self._timer_thread.start()

    def _flush_loop(self) -> None:
        """백그라운드에서 주기적으로 완료된 캡처를 플러시한다."""
        while not self._shutdown.wait(timeout=self._flush_interval):
            with self._lock:
                self._flush_completed(time.time())

    def emit(self, record: logging.LogRecord) -> None:
        try:
            with self._lock:
                # 1. 링 버퍼에 추가
                self._buffer.append((record.created, record))
                self._prune_buffer(record.created)

                # 2. 진행 중인 캡처에 레코드 추가
                for capture in self._active_captures.values():
                    capture["records"].append(record)

                # 3. 완료된 캡처 플러시
                self._flush_completed(record.created)

                # 4. WARNING/ERROR 발생 시 새 캡처 시작
                if record.levelno >= logging.WARNING:
                    self._start_capture(record)
        except Exception:
            self.handleError(record)

    def _prune_buffer(self, now: float) -> None:
        """버퍼에서 context_seconds * 2 이상 오래된 레코드 제거."""
        cutoff = now - (self.context_seconds * 2)
        while self._buffer and self._buffer[0][0] < cutoff:
            self._buffer.popleft()

    def _start_capture(self, trigger_record: logging.LogRecord) -> None:
        user_label = getattr(trigger_record, "user_label", "anonymous")
        dt = datetime.fromtimestamp(trigger_record.created)
        date_str = dt.strftime("%Y-%m-%d")
        time_str = dt.strftime("%Y-%m-%d_%H-%M-%S")
        level = trigger_record.levelname

        file_path = self.base_dir / date_str / user_label / f"{time_str}_{level}.log"

        # 과거 context_seconds 분의 로그를 버퍼에서 추출
        cutoff = trigger_record.created - self.context_seconds
        past_records = [r for t, r in self._buffer if t >= cutoff]

        capture_id = f"{time_str}_{level}_{id(trigger_record)}"
        self._active_captures[capture_id] = {
            "end_time": trigger_record.created + self.context_seconds,
            "records": list(past_records),
            "file_path": file_path,
        }

    def _flush_completed(self, now: float) -> None:
        completed = [cid for cid, cap in self._active_captures.items() if now >= cap["end_time"]]
        for cid in completed:
            cap = self._active_captures.pop(cid)
            self._write_capture(cap)

    def _write_capture(self, capture: dict) -> None:
        file_path: Path = capture["file_path"]
        records: list[logging.LogRecord] = capture["records"]
        if not records:
            return

        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(self.format(record) + "\n")

    def close(self) -> None:
        # 백그라운드 타이머 정지
        self._shutdown.set()
        self._timer_thread.join(timeout=5)
        with self._lock:
            # 종료 시 미완료 캡처 모두 플러시
            for cap in self._active_captures.values():
                self._write_capture(cap)
            self._active_captures.clear()
            self._buffer.clear()
        super().close()


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


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

    # ------------------------------------------------------------------
    # 1) dictConfig로 포매터, 필터, 콘솔 핸들러 설정
    # ------------------------------------------------------------------
    config: dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "readable": {
                "format": (
                    "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(user_label)s | %(name)s | %(message)s"
                ),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": JsonFormatter,
            },
        },
        "filters": {
            "user_label_filter": {
                "()": UserLabelFilter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": console_formatter,
                "filters": ["user_label_filter"],
                "stream": "ext://sys.stderr",
            },
        },
        "loggers": {
            "agent": {
                "level": effective_level,
                "handlers": ["console"],
                "propagate": False,
            },
            "app.backend": {
                "level": effective_level,
                "handlers": ["console"],
                "propagate": False,
            },
            "shared": {
                "level": effective_level,
                "handlers": ["console"],
                "propagate": False,
            },
            "sqlalchemy": {
                "level": os.getenv("LOG_LEVEL_SQLALCHEMY", "WARNING"),
                "handlers": ["console"],
                "propagate": False,
            },
            "httpx": {
                "level": os.getenv("LOG_LEVEL_HTTPX", "WARNING"),
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": ["console"],
                "propagate": False,
            },
        },
        "root": {
            "level": "WARNING",
            "handlers": ["console"],
        },
    }

    logging.config.dictConfig(config)

    # ------------------------------------------------------------------
    # 2) 커스텀 파일 핸들러를 프로그래밍 방식으로 등록
    # ------------------------------------------------------------------
    if is_production:
        file_formatter = JsonFormatter()
    else:
        file_formatter = logging.Formatter(
            fmt="%(asctime)s.%(msecs)03d | %(levelname)-8s | %(user_label)s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    user_label_filter = UserLabelFilter()

    # 일반 로그 핸들러 (날짜/유저별 폴더, 72시간 보존)
    general_handler = DailyUserFileHandler(base_dir=log_dir, retention_hours=72)
    general_handler.setFormatter(file_formatter)
    general_handler.addFilter(user_label_filter)

    # 에러/워닝 컨텍스트 핸들러 (±3분 컨텍스트, 30초마다 백그라운드 플러시)
    error_handler = ErrorContextHandler(
        base_dir=log_dir, context_minutes=3, flush_interval_sec=30.0
    )
    error_handler.setFormatter(file_formatter)
    error_handler.addFilter(user_label_filter)

    # 프로젝트 로거에 파일 핸들러 추가
    for logger_name in (
        "agent",
        "app.backend",
        "shared",
        "sqlalchemy",
        "httpx",
        "uvicorn",
        "uvicorn.access",
    ):
        lgr = logging.getLogger(logger_name)
        lgr.addHandler(general_handler)
        lgr.addHandler(error_handler)

    # root 로거에도 추가
    root = logging.getLogger()
    root.addHandler(general_handler)
    root.addHandler(error_handler)

    logger = logging.getLogger("shared.logging_config")
    logger.info(
        "Logging initialized: level=%s, environment=%s, log_dir=%s",
        effective_level,
        environment,
        log_dir,
    )
