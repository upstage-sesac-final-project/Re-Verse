"""OG agent v2 Interactive REPL — 로컬 테스트용.

사용법:
    python test_repl.py [--game-id game_001]
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


async def run(game_id: str = "game_001") -> None:
    from agent.graph.workflow import graph

    conversation_history: list[dict] = []

    print("=" * 60)
    print(f"  OG Agent v2 REPL (game: {game_id})")
    print("  'quit' 으로 종료")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n[User] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            break
        if not user_input:
            continue

        state: dict[str, Any] = {
            "user_input": user_input,
            "game_id": game_id,
            "conversation_history": conversation_history,
            "retry_count": 0,
        }

        try:
            result = await graph.ainvoke(state)
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()
            continue

        # ── 결과 출력 ──
        _print_result(result)

        # 대화 이력
        final = result.get("final_response", "")
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": final})


def _print_result(result: dict) -> None:
    intent = result.get("intent", "?")
    success = result.get("success")

    print()
    print("=" * 50)
    print(f"  intent={intent}  success={success}")
    print("=" * 50)

    # Operations (definition IR)
    ops = result.get("operation_tuples", [])
    if ops:
        print(f"\n--- Operations ({len(ops)}) ---")
        for i, op in enumerate(ops):
            subj = (op.get("subject") or {}).get("name", "?")
            print(f"  [{i}] {op.get('op','?')} {op.get('file','?')} subject='{subj}' field={op.get('field')}")
            val = op.get("value")
            if val:
                print(f"       value={val}")

    # Plan
    plan = result.get("execution_plan", [])
    if plan:
        print(f"\n--- Plan ({len(plan)} steps) ---")
        for s in plan:
            sid = s.get("step_id", "?")
            act = s.get("action_type", "?")
            tf = s.get("target_file", "?")
            desc = s.get("description", "")
            deps = s.get("depends_on", [])
            ti = s.get("target_info", {})
            print(f"  step {sid}: {tf}.{act}")
            if desc:
                print(f"    desc: {desc}")
            if deps:
                print(f"    deps: {deps}")
            print(f"    target: {json.dumps(ti, ensure_ascii=False)[:200]}")

    # Execution
    log = result.get("changes_log", [])
    if log:
        ok = sum(1 for e in log if e.get("success"))
        fail = len(log) - ok
        print(f"\n--- Execution ({ok} ok, {fail} failed) ---")
        for entry in log:
            sid = entry.get("step_id", "?")
            tf = entry.get("target_file", "?")
            act = entry.get("action", "?")
            succ = entry.get("success", False)
            err = entry.get("error")
            eid = entry.get("entity_id")
            data = entry.get("data")
            mods = entry.get("modified_files", [])
            print(f"  step {sid} {tf}.{act}: {'OK' if succ else 'FAIL'}", end="")
            if eid is not None:
                print(f" (id={eid})", end="")
            print()
            if err:
                print(f"    error: {err}")
            if mods:
                print(f"    modified: {mods}")
            if data and isinstance(data, dict):
                for k in ("name", "id", "traits", "effects", "params", "equips",
                           "classId", "actions", "dropItems", "learnings"):
                    if k in data:
                        v = json.dumps(data[k], ensure_ascii=False) if isinstance(data[k], (list, dict)) else str(data[k])
                        if len(v) > 150:
                            v = v[:150] + "..."
                        print(f"    {k}: {v}")

    # Validation
    if result.get("validation_summary"):
        print(f"\n--- Validation ---")
        print(f"  {result['validation_summary']}")

    # Response
    print(f"\n--- Response ---")
    print(result.get("final_response", "(응답 없음)"))


def main() -> None:
    game_id = "game_001"
    for i, arg in enumerate(sys.argv):
        if arg == "--game-id" and i + 1 < len(sys.argv):
            game_id = sys.argv[i + 1]
    asyncio.run(run(game_id))


if __name__ == "__main__":
    main()
