"""1번(Router) 및 2번(Definition) 노드 통합 인터랙티브 테스트."""

import asyncio
import logging

from agent.core.llm_client import reset_llm
from agent.graph.nodes.definition import definition
from agent.graph.nodes.router import router

# 로그 레벨 조정 (상세 로그를 원치 않으면 INFO로 변경)
logging.basicConfig(level=logging.ERROR)


async def main():
    print("\n" + "="*80)
    print(" [Interactive Test] Node 1 (Router) + Node 2 (Definition)")
    print("="*80)
    print(" - 'exit' 또는 'q'를 입력하면 종료됩니다.")
    print(" - 예시: '주인공에게 파이어볼 추가해줘', '포션 가격 500골드로 수정해줘'")
    
    game_id = "game_001"
    
    while True:
        try:
            user_input = input("\n[User Query] 입력: ").strip()
            if not user_input or user_input.lower() in ["exit", "q"]:
                break
                
            reset_llm()
            print(f"[*] '{user_input}'에 대한 분석을 시작합니다...")
            
            # 초기 상태
            state = {
                "user_input": user_input,
                "game_id": game_id,
                "conversation_history": []
            }
            
            # --- 1단계: Router ---
            router_output = await router(state)
            state.update(router_output)
            
            print(f"  [Router] 의도: {state.get('intent')} (신뢰도: {state.get('confidence', 0.0):.2f})")
            
            # 만약 Router에서 즉시 응답이 나왔거나 (추가 정보 필요 등) 의도가 2번으로 갈 수 없는 경우
            if state.get("intent") not in ["게임_요소_생성", "게임_요소_수정", "게임_요소_조회"]:
                print(f"  [Router Response]: {state.get('final_response', '진행할 수 없는 의도입니다.')}")
                continue
                
            # --- 2단계: Definition ---
            print("  [Definition] 분석 중 (ID 매핑 및 수정 계획 수립)...")
            definition_output = await definition(state)
            
            # 결과 출력
            print("\n" + "-"*50)
            print(" [Definition 결과 요약]")
            print("-"*50)
            
            if not definition_output.get("params_sufficient"):
                print(f"[!] 정보 부족: {definition_output.get('final_response')}")
            else:
                mods = definition_output.get("modifications", [])
                print(f"[*] 총 {len(mods)}개의 수정 단계가 식별되었습니다.")
                for i, mod in enumerate(mods, 1):
                    print(f"\n({i}) 파일: {mod['file']} | 액션: {mod['action']}")
                    print(f"    대상: {mod['target_entity']['category']} (ID: {mod['target_entity']['id']})")
                    if mod.get('action_object'):
                        print(f"    객체: {mod['action_object']['category']} (ID: {mod['action_object']['id']})")
                    print(f"    필드: {mod.get('target_field')} -> {mod.get('new_value')}")
                    print(f"    추론: {mod.get('thought_process')}")

        except Exception as e:
            print(f"\n[!] 오류 발생: {e}")
            # traceback.print_exc() # 필요시 주석 해제

if __name__ == "__main__":
    asyncio.run(main())
