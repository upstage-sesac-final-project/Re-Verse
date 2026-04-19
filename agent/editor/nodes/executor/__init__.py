"""executor 패키지 — Phase F 분해 뼈대.

기존 단일 파일 `executor.py` 를 패키지로 승격. Phase F 본체 (handlers/, orchestrator,
changelog, snapshot 등) 는 후속 sprint 에서 core.py 로부터 점진적으로 이주 예정.

현재 구조:
    __init__.py    — entry point 재export (기존 import path 호환)
    core.py        — 기존 executor.py 전체 로직 (분해 대상)
    mcp_registry.py — MCP_TOOL_MAP / 관련 해결자를 core 에서 분리

향후 이주 계획 (YB.md 6-3):
    executor/
      orchestrator.py   — depends_on 순회, handler 디스패치
      routing.py        — target_file + op → handler 매핑
      handlers/
        base.py
        actors.py       — Actors 특수 로직
        events.py       — Map / Common / Troop 통합
        system.py
        items.py
        enemies.py
        skills.py
        mapinfos.py
        weapons_armors.py
        classes_states.py
      changelog.py      — _enrich_changes_log_entry 표준화
      snapshot.py       — backup / snapshot 분리
"""

from agent.editor.nodes.executor import core as _core
from agent.editor.nodes.executor.core import executor

__all__ = ["executor"]


def __getattr__(name: str):
    """기존 `agent.editor.nodes.executor` 단일 파일이던 시절의 내부 심볼
    (예: `_sanitize_mz_item_effects_for_schema`, `MCP_TOOL_MAP`, 각종 헬퍼)
    을 패키지 네임스페이스에서 그대로 꺼낼 수 있도록 위임한다.

    후속 sprint 에서 core 를 handlers/ 로 분해할 때 공개 API 를 재정의하면
    이 shim 은 제거된다.
    """
    try:
        return getattr(_core, name)
    except AttributeError as e:
        raise AttributeError(
            f"module 'agent.editor.nodes.executor' has no attribute {name!r}"
        ) from e
