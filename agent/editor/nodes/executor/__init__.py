"""executor 패키지 — Task 16 에서 executor_v2 로 최종 이양.

본체 통합 sprint 마지막에 workflow 진입점을 `executor_v2.executor` 로 전환했다.
core.py 는 이제 dead (내부 심볼만 test 호환용으로 노출) — 차기 sprint 에서
완전 삭제 예정.

구조:
    __init__.py    — entry point = executor_v2.executor (runtime 경로)
    core.py        — legacy (dead; 내부 심볼 test 호환용으로만 유지)
    mcp_registry.py — MCP_TOOL_MAP (dead; MCP 경로 자체가 비활성)
"""

from agent.editor.nodes.executor import core as _core

# Task 16: runtime 진입점을 executor_v2 로 전환. core.executor 는 더 이상 호출되지 않음.
from agent.editor.nodes.executor_v2 import executor

__all__ = ["executor"]


def __getattr__(name: str):
    """legacy core 내부 심볼 호환 shim — test_mcp 등 내부 이름 참조 대응.
    runtime 경로에는 영향 없음. 차기 sprint 에서 core.py 제거 시 함께 제거.
    """
    try:
        return getattr(_core, name)
    except AttributeError as e:
        raise AttributeError(
            f"module 'agent.editor.nodes.executor' has no attribute {name!r}"
        ) from e
