"""Reader 노드 인터랙티브 테스트.

실행 방법:
    uv run python agent/tests/test_reader.py
"""

import asyncio
import json
import logging
import os
import sys

sys.path.append(os.getcwd())

from agent.graph.nodes.reader import reader

logging.basicConfig(level=logging.INFO)


async def run_interactive_test():
    print("\n" + "=" * 80)
    print(" [Interactive Test] Reader Node 검증 도구")
    print(" - 종료하려면 'exit' 또는 'q'를 입력하세요.")
    print("=" * 80)

    game_id = "game_001"

    while True:
        print("\n" + "-" * 40)
        user_input = input("[User Query] 입력: ").strip()

        if user_input.lower() in ["exit", "q", "quit"]:
            print("[*] 테스트를 종료합니다.")
            break

        if not user_input:
            continue

        state = {
            "user_input": user_input,
            "game_id": game_id,
            "conversation_history": [],
        }

        print(f"[*] '{user_input}' 처리 중...")

        try:
            result = await reader(state)
            print("\n" + "=" * 80)
            print(" [Node Output] 조회 결과")
            print("=" * 80)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        except Exception as e:
            print(f"\n[!] 오류 발생: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_test())
    except KeyboardInterrupt:
        print("\n[*] 사용자에 의해 중단되었습니다.")
