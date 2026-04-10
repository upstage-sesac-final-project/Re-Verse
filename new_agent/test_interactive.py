"""Interactive REPL — new-agent 워크플로우를 대화형으로 테스트.

사용법:
    python -m new_agent.test_interactive [--game-id game_001]
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any


async def run_interactive(game_id: str = "game_001") -> None:
    from new_agent.workflow import graph

    conversation_history: list[dict] = []

    print("=" * 60)
    print(f"  new-agent Interactive REPL (game: {game_id})")
    print("  'quit' 또는 'exit' 으로 종료")
    print("=" * 60)

    while True:
        try:
            user_input = input("\n[User] ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n종료합니다.")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("종료합니다.")
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
        final = result.get("final_response", "(응답 없음)")
        kind = result.get("kind", "?")
        success = result.get("success")
        resolved = result.get("resolved_input", "")

        print()
        print("=" * 50)
        print(f"  RESULT  kind={kind}  success={success}")
        print("=" * 50)

        # 1. Intake
        print(f"\n--- Intake ---")
        print(f"  resolved : {resolved or '(없음)'}")
        print(f"  kind     : {kind}")
        if result.get("clarification_question"):
            print(f"  question : {result['clarification_question']}")

        # 2. Operations (intake 추출 결과)
        ops = result.get("operation_tuples", [])
        if ops:
            print(f"\n--- Operations ({len(ops)}) ---")
            for i, op in enumerate(ops):
                subj = (op.get("subject") or {}).get("name", "?")
                val = op.get("value") or {}
                print(f"  [{i}] {op.get('op','?')} {op.get('file','?')}")
                print(f"       subject = '{subj}'")
                print(f"       field   = {op.get('field')}")
                print(f"       value   = {val}")

        # 3. Plan
        plan = result.get("execution_plan", [])
        if plan:
            print(f"\n--- Plan ({len(plan)} steps) ---")
            for s in plan:
                sid = s.get("step_id", "?")
                act = s.get("action_type", "?")
                tf = s.get("target_file", "?")
                desc = s.get("description", "")
                deps = s.get("depends_on", [])
                needs_profile = s.get("_needs_profiling", False)
                ti = s.get("target_info", {})
                print(f"  step {sid}: {tf}.{act}")
                print(f"    desc     : {desc}")
                if deps:
                    print(f"    deps     : {deps}")
                if needs_profile:
                    print(f"    profiling: YES")
                print(f"    target   : {json.dumps(ti, ensure_ascii=False)[:200]}")

        # 4. Execution
        log = result.get("changes_log", [])
        if log:
            ok = sum(1 for e in log if e.get("success"))
            fail = len(log) - ok
            print(f"\n--- Execution ({ok} ok, {fail} failed) ---")
            for entry in log:
                sid = entry.get("step_id", "?")
                act = entry.get("action", "?")
                tf = entry.get("target_file", "?")
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
                    print(f"    error    : {err}")
                if mods:
                    print(f"    modified : {mods}")
                if data and isinstance(data, dict):
                    # 핵심 필드만 요약
                    summary_keys = ["name", "id", "traits", "effects", "params",
                                    "equips", "classId", "actions", "dropItems",
                                    "updated_ids", "system_key", "value",
                                    "deleted_id", "key_path"]
                    shown = {k: data[k] for k in summary_keys if k in data}
                    if shown:
                        for k, v in shown.items():
                            v_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else str(v)
                            if len(v_str) > 150:
                                v_str = v_str[:150] + "..."
                            print(f"    {k}: {v_str}")

        # 5. Validation
        if result.get("validation_summary"):
            print(f"\n--- Validation ---")
            print(f"  {result['validation_summary']}")

        # 6. Response
        print(f"\n--- Response ---")
        print(final)

        # 대화 이력 업데이트
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": final})


def main() -> None:
    game_id = "game_001"
    for i, arg in enumerate(sys.argv):
        if arg == "--game-id" and i + 1 < len(sys.argv):
            game_id = sys.argv[i + 1]
    asyncio.run(run_interactive(game_id))


if __name__ == "__main__":
    main()
