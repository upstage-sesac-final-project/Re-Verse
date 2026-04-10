"""new-agent LangGraph 워크플로우 배선.

5노드: intake → planner → profiler → executor → validator → END

profiler 는 create step 이 없으면 skip.
validator 내부에서 partial retry loop 실행 (backedge 없음).
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from new_agent.state import AgentState


# ── 노드 함수 import ──────────────────────────

async def _intake_node(state: AgentState) -> dict:
    from new_agent.nodes.intake import intake
    return await intake(state)


async def _planner_node(state: AgentState) -> dict:
    from new_agent.nodes.planner import planner
    return planner(state)


async def _profiler_node(state: AgentState) -> dict:
    from new_agent.nodes.profiler import profiler
    return await profiler(state)


async def _executor_node(state: AgentState) -> dict:
    from new_agent.executor import executor
    return await executor(state)


async def _validator_node(state: AgentState) -> dict:
    from new_agent.nodes.validator import validator
    return await validator(state)


# ── 라우팅 함수 ─────────────────────────────────

def _route_after_intake(state: AgentState) -> str:
    """intake 후 kind 에 따라 분기."""
    kind = state.get("kind", "need_more_info")
    if kind == "actionable":
        return "planner"
    return "__end__"


def _route_after_planner(state: AgentState) -> str:
    """plan 에 create step 이 있으면 profiler, 없으면 executor 직행."""
    plan = state.get("execution_plan", [])
    has_create = any(s.get("_needs_profiling") for s in plan)
    if has_create:
        return "profiler"
    return "executor"


# ── 그래프 빌드 ─────────────────────────────────

def build_graph() -> StateGraph:
    """new-agent 워크플로우 그래프를 구성하고 컴파일한다.

    흐름:
        START
          └→ intake
               ├→ (non-actionable) → END
               └→ planner
                    ├→ (has create) → profiler → executor → validator → END
                    └→ (no create) → executor → validator → END
    """
    builder = StateGraph(AgentState)

    # 노드 등록
    builder.add_node("intake", _intake_node)
    builder.add_node("planner", _planner_node)
    builder.add_node("profiler", _profiler_node)
    builder.add_node("executor", _executor_node)
    builder.add_node("validator", _validator_node)

    # 진입점
    builder.add_edge(START, "intake")

    # 조건부 엣지
    builder.add_conditional_edges(
        "intake",
        _route_after_intake,
        {"planner": "planner", "__end__": END},
    )
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"profiler": "profiler", "executor": "executor"},
    )

    # 선형 엣지
    builder.add_edge("profiler", "executor")
    builder.add_edge("executor", "validator")
    builder.add_edge("validator", END)

    return builder.compile()


# 싱글톤
graph = build_graph()
