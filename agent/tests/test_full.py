"""1~6번 노드 전체 사이클 통합 테스트 (End-to-End) - No Pytest Version."""

import asyncio
import logging
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from agent.graph.state import AgentState
from agent.graph.workflow import graph
from agent.monitoring.langsmith_setup import setup_langsmith

# LangSmith 추적 활성화
setup_langsmith()

# 로깅 비활성화 (깔끔한 출력을 위해)
logging.basicConfig(level=logging.ERROR)


async def run_full_test():
    print("=" * 80)
    print(" [Re:Verse Agent] 1~6단계 전 과정 통합 테스트 (E2E)")
    print(" - 실행 흐름: Router -> Definition -> Planner -> Executor -> Validator -> Synthesizer")
    print(" - 종료하려면 'q' 또는 'exit'를 입력하세요.")
    print("=" * 80)

    game_id = "game_001"

    while True:
        try:
            user_input = input("\n[User Input]: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ["q", "exit", "quit"]:
                break

            # 초기 상태 설정
            initial_state: AgentState = {
                "user_input": user_input,
                "game_id": game_id,
                "conversation_history": [],
                "retry_count": 0,
                "changes_log": [],
                "tool_results": [],
            }

            print(f"\n[*] '{user_input}' 분석 및 실행 시작...")

            # 그래프 실행 (스트리밍 모드)
            async for event in graph.astream(initial_state):
                for node_name, state_update in event.items():
                    if state_update is None:
                        continue

                    print(f"\n>>> [Node: {node_name}] 실행 완료")

                    # 노드별 핵심 정보 출력 (테스트용)
                    if node_name == "router":
                        print(
                            f"    - 파악된 의도: {state_update.get('intent')} (신뢰도: {state_update.get('confidence')})"
                        )

                    elif node_name == "definition":
                        mods = state_update.get("modifications", [])
                        final_res = state_update.get("final_response")
                        if final_res:
                            print(f"    - 즉시 응답 생성됨: {final_res}")
                        print(f"    - 정의된 작업: {len(mods)}개")
                        for m in mods:
                            target_type = m.get("target", "unknown")
                            id_val = m["params"].get(f"{target_type}_id", "N/A")
                            print(f"      [{m['type'].upper()}] {target_type} (ID: {id_val})")

                    elif node_name == "planner":
                        plan = state_update.get("execution_plan", [])
                        print(f"    - 수립된 계획: {len(plan)}단계")
                        for i, step in enumerate(plan, 1):
                            target = step.get("target_file") or step.get("target", "unknown")
                            action = step.get("action_type") or step.get("task", "task")
                            desc = step.get("description", "설명 없음")
                            print(f"      {i}. [{action.upper()}] {target}: {desc}")

                    elif node_name == "executor":
                        logs = state_update.get("changes_log", [])
                        print(f"    - 실행 결과: {len(logs) if logs else 0}개의 작업 수행됨")
                        for i, log in enumerate(logs, 1):
                            status = "성공" if log.get("success") else "실패"
                            tool = log.get("tool_name", "unknown")
                            print(f"      ({i}) {tool}: {status}")
                            if not log.get("success"):
                                print(f"        에러: {log.get('error', '알 수 없는 오류')}")

                    elif node_name == "validator":
                        # Validator 노드의 내부 구조에 따라 success 필드 확인
                        val = state_update.get("validation_result", {})
                        passed = val.get("passed", False) if isinstance(val, dict) else False
                        status = "성공" if passed else "실패"
                        print(f"    - 검증 결과: {status}")

                    elif node_name == "synthesizer":
                        print("\n" + "-" * 50)
                        print(f"[Final Agent Response]\n{state_update.get('final_response')}")
                        print("-" * 50)

        except Exception as e:
            print(f"\n[!] 오류 발생: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(run_full_test())
    except KeyboardInterrupt:
        print("\n[*] 사용자에 의해 중단되었습니다.")
    except Exception as e:
        print(f"\n[!] 치명적 오류: {e}")
