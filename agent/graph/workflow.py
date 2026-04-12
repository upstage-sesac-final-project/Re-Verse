"""LangGraph StateGraph — Re:Verse 에이전트 워크플로우."""

from langgraph.graph import END, START, StateGraph

from agent.graph.nodes.definition import definition
from agent.graph.nodes.executor_v2 import executor as executor_v2
from agent.graph.nodes.game_index_resolve import game_index_resolve
from agent.graph.nodes.planner_v2 import planner_v2
from agent.graph.nodes.profiler import profiler
from agent.graph.nodes.reader import reader
from agent.graph.nodes.router import router
from agent.graph.nodes.synthesizer import synthesizer
from agent.graph.nodes.validator_v2 import validator as validator_v2
from agent.graph.routing import route_after_definition, route_after_router
from agent.graph.state import AgentState


def _route_after_planner(state: AgentState) -> str:
    """plan 에 create step 이 있으면 profiler, 없으면 executor 직행."""
    plan = state.get("execution_plan", []) or []
    has_create = any(s.get("_needs_profiling") for s in plan)
    return "profiler" if has_create else "executor"


def build_graph() -> StateGraph:
    """Re:Verse 에이전트 워크플로우 그래프를 구성하고 컴파일한다.

    흐름:
        START
          └→ router
               ├→ (clarification / chat / out_of_scope) → END
               ├→ reader → END
               └→ definition
                    ├→ (params 불충분) → END
                    └→ planner
                         └→ executor
                              └→ validator
                                   ├→ (실패 + retry < 2) → executor
                                   └→ synthesizer → END
    """
    builder = StateGraph(AgentState)

    # ── 노드 등록 ──────────────────────────────────────────
    builder.add_node("router", router)
    builder.add_node("reader", reader)
    builder.add_node("definition", definition)
    builder.add_node("game_index_resolve", game_index_resolve)
    builder.add_node("planner", planner_v2)
    builder.add_node("profiler", profiler)
    builder.add_node("executor", executor_v2)
    builder.add_node("validator", validator_v2)
    builder.add_node("synthesizer", synthesizer)

    # ── 진입점 ─────────────────────────────────────────────
    builder.add_edge(START, "router")

    # ── 조건부 엣지 ────────────────────────────────────────
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {"reader": "reader", "definition": "definition", "__end__": END},
    )
    builder.add_conditional_edges(
        "definition",
        route_after_definition,
        {"planner": "game_index_resolve", "__end__": END},
    )
    builder.add_edge("game_index_resolve", "planner")
    # validator_v2 는 내부에서 partial retry 처리. backedge 없이 항상 synthesizer 로.
    builder.add_edge("validator", "synthesizer")

    # planner → profiler 또는 executor (조건부)
    builder.add_conditional_edges(
        "planner",
        _route_after_planner,
        {"profiler": "profiler", "executor": "executor"},
    )

    # ── 선형 엣지 ──────────────────────────────────────────
    builder.add_edge("reader", END)
    builder.add_edge("profiler", "executor")
    builder.add_edge("executor", "validator")
    builder.add_edge("synthesizer", END)

    return builder.compile()


# 싱글톤 그래프 인스턴스
graph = build_graph()
