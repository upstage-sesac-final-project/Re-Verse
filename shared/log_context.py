"""로그 컨텍스트 — 요청별 유저 정보를 로깅에 전달하기 위한 contextvars.

로그 핸들러에서 유저별 폴더 분기에 사용된다.
폴더명 형식: {username}_{user_id} (예: genie_1)
"""

from contextvars import ContextVar

current_user_label: ContextVar[str] = ContextVar("current_user_label", default="anonymous")


def set_current_user(username: str, user_id: int) -> None:
    """로깅 컨텍스트에 유저 정보를 설정한다."""
    current_user_label.set(f"{username}_{user_id}")
