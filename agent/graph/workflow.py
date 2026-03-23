"""LangGraph StateGraph — Re:Verse 에이전트 워크플로우."""

from langgraph.graph import END, START, StateGraph

from agent.graph.nodes.definition import definition
from agent.graph.nodes.executor import executor
from agent.graph.nodes.planner import planner
from agent.graph.nodes.router import router
from agent.graph.nodes.synthesizer import synthesizer
from agent.graph.nodes.validator import validator
from agent.graph.routing import route_after_definition, route_after_router, route_after_validator
from agent.graph.state import AgentState


def build_graph() -> StateGraph:
    """Re:Verse 에이전트 워크플로우 그래프를 구성하고 컴파일한다.

    흐름:
        START
          └→ router
               ├→ (clarification / chat / out_of_scope) → END
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
    builder.add_node("definition", definition)
    builder.add_node("planner", planner)
    builder.add_node("executor", executor)
    builder.add_node("validator", validator)
    builder.add_node("synthesizer", synthesizer)

    # ── 진입점 ─────────────────────────────────────────────
    builder.add_edge(START, "router")

    # ── 조건부 엣지 ────────────────────────────────────────
    builder.add_conditional_edges(
        "router",
        route_after_router,
        {"definition": "definition", "__end__": END},
    )
    builder.add_conditional_edges(
        "definition",
        route_after_definition,
        {"planner": "planner", "__end__": END},
    )
    builder.add_conditional_edges(
        "validator",
        route_after_validator,
        {"synthesizer": "synthesizer", "executor": "executor"},
    )

    # ── 선형 엣지 ──────────────────────────────────────────
    builder.add_edge("planner", "executor")
    builder.add_edge("executor", "validator")
    builder.add_edge("synthesizer", END)

    return builder.compile()


# 싱글톤 그래프 인스턴스
graph = build_graph()
