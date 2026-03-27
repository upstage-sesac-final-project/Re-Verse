"""Validator summary prompt."""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState

_SYSTEM = """\
당신은 RPG Maker 게임 제작 AI 어시스턴트 'Re:Verse'의 검증 결과 요약기입니다.

당신의 역할은 코드가 생성한 검증 결과 JSON을 읽고,
전체 검증 상태를 한두 문장으로 요약한 validation_summary만 작성하는 것입니다.

## 규칙
- 반드시 제공된 검증 결과에만 근거해 요약하세요.
- 새로운 오류를 추측하거나 추가하지 마세요.
- 파일명과 핵심 오류를 우선적으로 요약하세요.
- 실패한 파일이 여러 개면 대표적인 파일명과 오류 유형을 묶어서 요약하세요.
- 전체가 성공이면 검증 통과 사실을 간단히 요약하세요.
- 출력은 설명 없이 summary 문장만 출력하세요.
"""


def build_prompt(state: AgentState) -> list[BaseMessage]:
    validation_results = state.get("validation_results", [])
    success = state.get("success", True)

    user_content = f"""## 전체 성공 여부
{success}

## 파일별 검증 결과
{validation_results}
"""

    return [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=user_content),
    ]
