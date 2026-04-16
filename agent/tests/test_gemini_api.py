import asyncio
import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
sys.path.append(str(Path(__file__).resolve().parents[0]))


from agent.core.llm_client import agent_config, invoke_llm_simple


async def test_gemini():
    print("--- Gemini API Test ---")
    print(f"Model: {agent_config.LLM_MODEL}")
    print(f"Base URL: {agent_config.LLM_BASE_URL}")
    # API 키 앞부분만 출력 (보안)
    key = agent_config.LLM_API_KEY
    masked_key = f"{key[:8]}...{key[-4:]}" if len(key) > 12 else "INVALID_KEY"
    print(f"API Key: {masked_key}")

    try:
        print("\nSending test message: '안녕, 너는 누구니?'")
        response = await invoke_llm_simple(
            system_prompt="You are a helpful assistant.",
            user_message="안녕, 너는 누구니? 짧게 대답해줘.",
        )
        print(f"\nResponse from Gemini:\n{response}")
        print("\n✅ API Test Success!")
    except Exception as e:
        print("\n❌ API Test Failed!")
        print(f"Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_gemini())
