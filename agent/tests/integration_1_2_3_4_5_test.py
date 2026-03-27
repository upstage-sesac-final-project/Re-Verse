"""Interactive integration test for Router -> Definition -> Planner -> Executor -> Validator."""

import asyncio
import logging
import sys
import traceback
from pathlib import Path
from typing import Any

from agent.core.llm_client import reset_llm
from agent.graph.nodes.definition import definition
from agent.graph.nodes.executor import executor
from agent.graph.nodes.planner import planner
from agent.graph.nodes.router import router
from agent.graph.nodes.validator import validator

ROOT_PATH = str(Path(__file__).resolve().parents[2])
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)

logging.basicConfig(level=logging.ERROR)

SUPPORTED_INTENTS = {
    "게임_요소_생성",
    "게임_요소_수정",
    "게임_요소_조회",
}


def build_validation_result_compat(state: dict[str, Any]) -> dict[str, Any]:
    validation_results = state.get("validation_results", [])
    flattened_errors = [error for item in validation_results for error in item.get("errors", [])]
    error_count = sum(int(item.get("error_count", 0)) for item in validation_results)
    return {
        "passed": state.get("success", False),
        "errors": flattened_errors,
        "error_count": error_count,
    }


def print_router_result(state: dict[str, Any]) -> None:
    print("\n[1. Router Result]")
    print(f"  [*] intent: {state.get('intent')} (confidence={state.get('confidence', 0.0):.2f})")
    if state.get("intent") not in SUPPORTED_INTENTS:
        print(
            f"  [*] response: {state.get('final_response', 'No executable intent was returned.')}"
        )


def print_definition_result(state: dict[str, Any]) -> None:
    print("\n[2. Definition Result]")
    print(f"  [*] params_sufficient: {state.get('params_sufficient', False)}")

    if not state.get("params_sufficient"):
        print(f"  [*] response: {state.get('final_response', '(missing response)')}")
        return

    modifications = state.get("modifications", [])
    print(f"  [*] Modifications defined: {len(modifications)}")
    for modification in modifications:
        print(
            f"    - [{str(modification.get('type', '')).upper()}] "
            f"{modification.get('target')} "
            f"(params: {modification.get('params')})"
        )
    print(f"  [*] Extracted IDs: {state.get('extracted_ids')}")


def print_planner_result(state: dict[str, Any]) -> None:
    print("\n[3. Planner Result]")
    execution_plan = state.get("execution_plan", [])
    print(f"  [*] Planned steps: {len(execution_plan)}")

    if not execution_plan:
        print("  [!] No execution_plan entries found.")
        return

    for index, step in enumerate(execution_plan, start=1):
        print(
            f"    - {index}: {step.get('target_file')} "
            f"{step.get('action_type')} "
            f"({step.get('description')})"
        )


def print_executor_result(state: dict[str, Any]) -> None:
    changes = state.get("changes_log", [])
    print("\n[4. Executor Result]")

    if not changes:
        print("  [!] No executor changes_log entries found.")
        return

    for log in changes:
        status = "SUCCESS" if log.get("success") else "FAILED"
        tool = log.get("tool_name", "unknown_tool")
        step_num = log.get("step_id") or log.get("step", "?")
        print(f"  ({step_num}) {tool}: {status}")

        if not log.get("success"):
            error_message = log.get("error") or log.get("stderr") or "Unknown error"
            print(f"      error: {error_message}")
            continue

        output = log.get("stdout") or "completed"
        print(f"      result: {output}")

    backup_paths = state.get("backup_paths", {})
    if backup_paths:
        print(f"  [*] Backup files: {len(backup_paths)}")


def print_validator_result(state: dict[str, Any]) -> None:
    print("\n[5. Validator Result]")
    print(f"  [*] Summary: {state.get('validation_summary', '(missing summary)')}")
    print(f"  [*] Success: {state.get('success', False)}")

    validation_results = state.get("validation_results", [])
    if not validation_results:
        print("  [!] No validation_results entries found.")
        return

    for item in validation_results:
        target = item.get("target", "(unknown)")
        status = "SUCCESS" if item.get("success") else "FAILED"
        message = item.get("message", "")
        error_count = item.get("error_count", 0)
        print(f"  - {target}: {status} | errors={error_count}")
        if message:
            print(f"      message: {message}")

        if item.get("backup_path"):
            print(f"      backup: {item['backup_path']}")

        related_steps = item.get("related_steps")
        if related_steps:
            print(f"      related_steps: {related_steps}")

        for error in item.get("errors", []):
            location = error.get("loc", "$")
            detail = error.get("msg", error)
            print(f"      error: {location} -> {detail}")


async def main() -> None:
    print("\n" + "=" * 80)
    print(" [Integration Test] Nodes 1-5 (Full Pipeline)")
    print("=" * 80)
    print(" 1. Router -> 2. Definition -> 3. Planner -> 4. Executor -> 5. Validator")
    print(" - Enter 'exit' or 'q' to quit")

    game_id = "game_001"

    while True:
        try:
            user_input = input("\n[User Query] Input: ").strip()
            if not user_input or user_input.lower() in {"exit", "q"}:
                break

            reset_llm()
            print(f"[*] Starting pipeline for: {user_input}")

            state: dict[str, Any] = {
                "user_input": user_input,
                "game_id": game_id,
                "conversation_history": [],
                "retry_count": 0,
            }

            print("\n[Step 1] Router")
            router_output = await router(state)
            state.update(router_output)
            print(
                f"  [Router] intent={state.get('intent')} "
                f"(confidence={state.get('confidence', 0.0):.2f})"
            )

            if state.get("intent") not in SUPPORTED_INTENTS:
                print("\n" + "-" * 50)
                print(" [Integration Test Result]")
                print("-" * 50)
                print_router_result(state)
                continue

            print("\n[Step 2] Definition")
            definition_output = await definition(state)
            state.update(definition_output)

            if not state.get("params_sufficient"):
                print("\n" + "-" * 50)
                print(" [Integration Test Result]")
                print("-" * 50)
                print_router_result(state)
                print_definition_result(state)
                continue

            modifications = state.get("modifications", [])
            print(f"  [*] Modifications defined: {len(modifications)}")
            for modification in modifications:
                print(
                    f"    - [{str(modification.get('type', '')).upper()}] "
                    f"{modification.get('target')} "
                    f"(params: {modification.get('params')})"
                )
            print(f"  [*] Extracted IDs: {state.get('extracted_ids')}")

            print("\n[Step 3] Planner")
            planner_output = await planner(state)
            state.update(planner_output)

            execution_plan = state.get("execution_plan", [])
            print(f"  [*] Planned steps: {len(execution_plan)}")
            for index, step in enumerate(execution_plan, start=1):
                print(
                    f"    - {index}: {step.get('target_file')} "
                    f"{step.get('action_type')} "
                    f"({step.get('description')})"
                )

            print("\n[Step 4] Executor")
            executor_output = await executor(state)
            state.update(executor_output)

            print("\n[Step 5] Validator")
            validator_output = await validator(state)
            state.update(validator_output)
            state["validation_result"] = build_validation_result_compat(state)

            print("\n" + "-" * 50)
            print(" [Integration Test Result]")
            print("-" * 50)
            print_router_result(state)
            print_definition_result(state)
            print_planner_result(state)
            print_executor_result(state)
            print_validator_result(state)

        except Exception as error:
            print(f"\n[!] Error occurred: {error}")
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
