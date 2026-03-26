"""1, 2, 3, 4번 노드 통합 인터랙티브 테스트 (Router -> Definition -> Planner -> Executor)."""

import asyncio
import logging
import sys
from pathlib import Path

# 프로젝트 루트를 경로에 추가 (실행 위치에 상관없이 import 가능하도록)
root_path = str(Path(__file__).resolve().parents[2])
if root_path not in sys.path:
    sys.path.append(root_path)

from agent.core.llm_client import reset_llm
from agent.graph.nodes.router import router
from agent.graph.nodes.definition import definition
from agent.graph.nodes.planner import planner
from agent.graph.nodes.executor import executor

# 로그 레벨 조정 (상세 로그를 원치 않으면 ERROR로 설정)
logging.basicConfig(level=logging.ERROR)

async def main():
    print("\n" + "="*80)
    print(" [Integration Test] Nodes 1-4 (Full Pipeline)")
    print("="*80)
    print(" 1. Router -> 2. Definition -> 3. Planner -> 4. Executor")
    print(" - 'exit' 또는 'q'를 입력하면 종료됩니다.")
    print(" - 예시: '주인공에게 파이어볼 추가해줘', '포션 가격 500골드로 수정해줘'")
    
    game_id = "game_001"
    
    while True:
        try:
            user_input = input("\n[User Query] 입력: ").strip()
            if not user_input or user_input.lower() in ["exit", "q"]:
                break
                
            reset_llm()
            print(f"[*] '{user_input}'에 대한 분석 및 실행을 시작합니다...")
            
            # 초기 상태
            state = {
                "user_input": user_input,
                "game_id": game_id,
                "conversation_history": [],
                "retry_count": 0
            }
            
            # --- 1단계: Router ---
            print("\n[Step 1] Router 진입")
            router_output = await router(state)
            state.update(router_output)
            print(f"  [Router] 의도: {state.get('intent')} (신뢰도: {state.get('confidence', 0.0):.2f})")
            
            if state.get("intent") not in ["게임_요소_생성", "게임_요소_수정", "게임_요소_조회"]:
                print(f"  [Router Response]: {state.get('final_response', '진행할 수 없는 의도입니다.')}")
                continue

            # --- 2단계: Definition ---
            print("\n[Step 2] Definition 진입")
            definition_output = await definition(state)
            state.update(definition_output)
            
            if not state.get("params_sufficient"):
                print(f"  [Definition Response]: {state.get('final_response')}")
                continue
            
            print(f"  [*] {len(state.get('modifications', []))}개의 수정 사항 정의됨:")
            for m in state.get('modifications', []):
                print(f"    - [{m['type'].upper()}] {m['target']} (params: {m['params']})")
            print(f"  [*] 추출된 ID: {state.get('extracted_ids')}")

            # --- 3단계: Planner ---
            print("\n[Step 3] Planner 진입")
            planner_output = await planner(state)
            state.update(planner_output)
            
            plan = state.get("execution_plan", [])
            print(f"  [*] {len(plan)}단계의 실행 계획 수립됨.")
            for i, step in enumerate(plan, 1):
                print(f"    - {i}단계: {step.get('target_file')} {step.get('action_type')} ({step.get('description')})")

            # --- 4단계: Executor ---
            print("\n[Step 4] Executor 진입")
            executor_output = await executor(state)
            state.update(executor_output)
            
            # 결과 출력
            print("\n" + "-"*50)
            print(" [Integration Test 결과]")
            print("-"*50)
            
            changes = state.get("changes_log", [])
            if not changes:
                print("[!] 실행된 변경 사항이 없습니다.")
            else:
                for log in changes:
                    status = "✅ 성공" if log.get("success") else "❌ 실패"
                    tool = log.get("tool_name", "unknown_tool")
                    # 'step_id' 또는 'step' 키를 사용하여 순서 표시
                    step_num = log.get("step_id") or log.get("step", "?")
                    print(f"({step_num}) {tool}: {status}")
                    
                    if not log.get("success"):
                        err = log.get("error") or log.get("stderr") or "알 수 없는 에러"
                        print(f"    에러: {err}")
                    else:
                        out = log.get("stdout") or "수행 완료"
                        print(f"    결과: {out}")

            if state.get("backup_paths"):
                print(f"\n[*] 백업 생성됨: {len(state['backup_paths'])}개 파일")

        except Exception as e:
            print(f"\n[!] 오류 발생: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
