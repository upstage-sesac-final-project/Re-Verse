import asyncio
import json
import logging
import os
import sys

# 프로젝트 루트를 경로에 추가
sys.path.append(os.getcwd())

from agent.core.llm_client import reset_llm
from agent.graph.nodes.definition import definition

# 로깅 설정 (필요에 따라 INFO 또는 DEBUG로 조절 가능)
logging.basicConfig(level=logging.WARNING)

async def run_interactive_test():
    """사용자로부터 직접 입력을 받아 Definition 노드를 테스트한다."""
    print("\n" + "="*80)
    print(" [Interactive Test] Definition Node (2단계) 검증 도구")
    print(" - 종료하려면 'exit' 또는 'q'를 입력하세요.")
    print("="*80)

    # LLM 초기화
    reset_llm()
    
    game_id = "game_001" # 기본 테스트용 게임 ID

    while True:
        print("\n" + "-"*40)
        user_input = input("[User Query] 입력: ").strip()
        
        if user_input.lower() in ['exit', 'q', 'quit']:
            print("[*] 테스트를 종료합니다.")
            break
            
        if not user_input:
            continue

        # 1. 초기 상태 설정
        initial_state = {
            "user_input": user_input,
            "game_id": game_id,
            "intent": "game_modify", # 기본 의도를 수정으로 설정
            "confidence": 1.0,
            "conversation_history": []
        }
        
        print(f"[*] '{user_input}'에 대한 분석을 시작합니다...")

        # 2. Definition 노드 실행
        try:
            # 노드 직접 호출
            node_result = await definition(initial_state)
            
            print("\n" + "="*80)
            print(" [Node Output] 분석 결과")
            print("="*80)
            print(json.dumps(node_result, indent=2, ensure_ascii=False))
            
        except Exception as e:
            print(f"\n[!] 오류 발생: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(run_interactive_test())
    except KeyboardInterrupt:
        print("\n[*] 사용자에 의해 중단되었습니다.")
