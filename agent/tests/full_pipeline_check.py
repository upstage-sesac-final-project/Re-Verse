"""전체 파이프라인 점검: Router(1) → Definition(2) → Planner(3) → Executor(4) → Validator(5).

한 번의 사용자 메시지로 각 단계가 어디까지 통과하는지 출력합니다.
(LLM·MCP·스토리지가 설정된 환경에서만 의미 있습니다.)

실행 예:

  # 한 번만 실행 (맵 관련 예시)
  GAME_ID=game_6530bbd1 uv run python -m agent.tests.full_pipeline_check \\
    --message "맵 목록 알려줘"

  # 대화형 (메시지 없이)
  GAME_ID=game_001 uv run python -m agent.tests.full_pipeline_check

종료 코드:
  0 — Validator까지 success=True
  1 — Executor/Validator 중 실패 또는 일부 스텝 실패
  2 — Router에서 실행 의도 아님(범위_외 등) 또는 Definition에서 params 부족
  3 — 예외 또는 필수 인자 누락
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import traceback
from pathlib import Path
from typing import cast

from agent.core.llm_client import reset_llm
from agent.graph.nodes.definition import definition
from agent.graph.nodes.executor import executor
from agent.graph.nodes.planner import planner
from agent.graph.nodes.router import router
from agent.graph.nodes.validator import validator
from agent.graph.state import AgentState

ROOT_PATH = str(Path(__file__).resolve().parents[2])
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)

logging.basicConfig(level=logging.ERROR)

SUPPORTED_INTENTS = frozenset(
    {
        "게임_요소_생성",
        "게임_요소_수정",
        "게임_요소_조회",
    }
)


def _print_header(title: str) -> None:
    print("\n" + "─" * 60)
    print(title)
    print("─" * 60)


async def run_full_pipeline(user_input: str, game_id: str) -> tuple[int, AgentState]:
    """1~5단계 실행 후 (exit_code, 최종 state) 반환."""
    state: AgentState = {
        "user_input": user_input,
        "game_id": game_id,
        "conversation_history": [],
        "retry_count": 0,
    }

    _print_header("[1] Router")
    router_output = await router(state)
    state.update(cast(AgentState, router_output))
    intent = state.get("intent")
    conf = state.get("confidence", 0.0)
    print(f"  intent={intent}  confidence={conf:.2f}")
    if intent not in SUPPORTED_INTENTS:
        print("  → 여기서 종료 (실행 파이프라인 미진입)")
        print(f"  final_response: {(state.get('final_response') or '')[:500]}")
        return 2, state

    _print_header("[2] Definition")
    definition_output = await definition(state)
    state.update(cast(AgentState, definition_output))
    ps = state.get("params_sufficient", False)
    print(f"  params_sufficient={ps}")
    if not ps:
        print("  → 여기서 종료")
        print(f"  final_response: {(state.get('final_response') or '')[:500]}")
        return 2, state

    mods = state.get("modifications") or []
    print(f"  modifications={len(mods)}  extracted_ids={state.get('extracted_ids')}")

    _print_header("[3] Planner")
    planner_output = await planner(state)
    state.update(cast(AgentState, planner_output))
    plan = state.get("execution_plan") or []
    print(f"  steps={len(plan)}")
    for i, step in enumerate(plan, start=1):
        print(
            f"    {i}. {step.get('target_file')}  {step.get('action_type')}  "
            f"{(step.get('description') or '')[:70]}"
        )
    if not plan:
        print("  [!] execution_plan 비어 있음 → Executor 의미 없음")
        return 2, state

    _print_header("[4] Executor")
    executor_output = await executor(state)
    state.update(cast(AgentState, executor_output))
    logs = state.get("changes_log") or []
    exec_fail = 0
    for log in logs:
        ok = log.get("success")
        tool = log.get("tool_name", "?")
        sid = log.get("step_id", "?")
        line = f"  step {sid}  {tool}  success={ok}"
        if ok is False:
            exec_fail += 1
            err = log.get("error") or log.get("stderr") or ""
            line += f"  | {str(err)[:120]}"
        print(line)

    _print_header("[5] Validator")
    validator_output = await validator(state)
    state.update(cast(AgentState, validator_output))
    v_ok = bool(state.get("success", False))
    print(f"  success={v_ok}")
    print(f"  validation_summary: {(state.get('validation_summary') or '')[:300]}")

    if exec_fail or not v_ok:
        return 1, state
    return 0, state


async def _interactive(game_id: str) -> int:
    print("\n" + "=" * 60)
    print(" 전체 파이프라인 점검 (1→5)  —  exit / q 로 종료")
    print("=" * 60)
    print(f" game_id={game_id}")
    last_code = 0
    while True:
        try:
            line = input("\n[메시지] ").strip()
        except EOFError:
            break
        if not line or line.lower() in {"exit", "q"}:
            break
        reset_llm()
        code, _ = await run_full_pipeline(line, game_id)
        last_code = code
        print(
            f"\n  → 종료 코드: {code}  (0=검증까지 성공, 2=라우터/정의 단계에서 중단, 1=실행/검증 실패)"
        )
    return last_code


def main() -> None:
    p = argparse.ArgumentParser(description="파이프라인 1~5단계 전체 점검")
    p.add_argument(
        "--game-id",
        default=None,
        help="게임 ID (기본: 환경 변수 GAME_ID, 없으면 game_001)",
    )
    p.add_argument(
        "--message",
        "-m",
        default=None,
        help="한 번만 실행할 사용자 메시지 (없으면 대화형)",
    )
    args = p.parse_args()

    import os

    game_id = (args.game_id or os.environ.get("GAME_ID") or "").strip() or "game_001"

    try:
        if args.message:
            reset_llm()
            code, _ = asyncio.run(run_full_pipeline(args.message.strip(), game_id))
            print(f"\n종료 코드: {code}")
            raise SystemExit(code)
        code = asyncio.run(_interactive(game_id))
        raise SystemExit(code)
    except SystemExit:
        raise
    except Exception as e:
        print(f"\n[!] 예외: {e}", file=sys.stderr)
        traceback.print_exc()
        raise SystemExit(3) from e


if __name__ == "__main__":
    main()
