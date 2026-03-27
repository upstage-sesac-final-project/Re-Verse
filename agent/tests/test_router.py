"""Router 노드 단위 테스트.

실행 방법:
    # 단위 테스트만 (LLM 호출 없음, 빠름)
    uv run pytest agent/tests/test_router.py -v

    # 실제 LLM 호출 포함 (API 키 필요)
    uv run pytest agent/tests/test_router.py -v -m integration -s
"""

from unittest.mock import AsyncMock, patch

import pytest

from agent.graph.nodes.router import _RouterOutput, router
from agent.graph.state import AgentState
from agent.prompts.router_prompt import build_prompt

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _mock_output(
    intent: str,
    confidence: float = 0.9,
    reasoning: str = "test",
    response: str = "",
) -> _RouterOutput:
    return _RouterOutput(
        intent=intent,
        confidence=confidence,
        reasoning=reasoning,
        response=response,
    )


def _state(user_input: str, history: list[dict] | None = None) -> AgentState:
    s: AgentState = {"user_input": user_input, "game_id": "test_game"}
    if history:
        s["conversation_history"] = history
    return s


# ── 프롬프트 빌더 테스트 ───────────────────────────────────────────────────────


class TestBuildPrompt:
    def test_returns_two_messages(self):
        msgs = build_prompt(_state("슬라임 만들어줘"))
        assert len(msgs) == 2

    def test_user_input_in_human_message(self):
        msgs = build_prompt(_state("슬라임 만들어줘"))
        assert "슬라임 만들어줘" in msgs[1].content

    def test_history_included_when_present(self):
        history = [
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "안녕하세요"},
        ]
        msgs = build_prompt(_state("슬라임 만들어줘", history=history))
        assert "안녕" in msgs[1].content

    def test_history_capped_at_five_turns(self):
        history = [{"role": "user", "content": f"msg{i}"} for i in range(10)]
        msgs = build_prompt(_state("테스트", history=history))
        # 최근 5개만 포함되므로 msg0~msg4는 없어야 함
        assert "msg0" not in msgs[1].content
        assert "msg9" in msgs[1].content

    def test_empty_history_no_history_section(self):
        msgs = build_prompt(_state("테스트"))
        assert "대화 이력" not in msgs[1].content


# ── 라우터 노드 단위 테스트 (LLM mock) ────────────────────────────────────────


class TestRouter:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("intent", ["게임_요소_생성", "게임_요소_수정", "게임_요소_조회"])
    async def test_action_intents_return_intent_and_confidence(self, intent):
        with patch("agent.graph.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(intent, confidence=0.95)
            result = await router(_state("테스트 입력"))

        assert result["intent"] == intent
        assert result["confidence"] == 0.95
        assert "final_response" not in result  # 액션 인텐트는 즉시 응답 없음

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "intent",
        ["추가_정보_필요", "일반_대화", "범위_외"],
    )
    async def test_terminal_intents_set_final_response(self, intent):
        expected_response = "이것은 응답입니다."
        with patch("agent.graph.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(intent, response=expected_response)
            result = await router(_state("테스트 입력"))

        assert result["intent"] == intent
        assert result["final_response"] == expected_response

    @pytest.mark.asyncio
    async def test_passes_correct_structured_output_type(self):
        with patch("agent.graph.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output("게임_요소_생성")
            await router(_state("새 적 만들어줘"))

        _, kwargs = mock_llm.call_args
        assert kwargs.get("structured_output") is _RouterOutput

    @pytest.mark.asyncio
    async def test_conversation_history_forwarded_to_prompt(self):
        history = [{"role": "user", "content": "이전 대화"}]
        with patch("agent.graph.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output("게임_요소_조회")
            await router(_state("현재 적 목록 보여줘", history=history))

        messages = mock_llm.call_args[0][0]
        assert any("이전 대화" in str(m.content) for m in messages)


# ── 통합 테스트 (실제 LLM 호출) ───────────────────────────────────────────────
# 실행: uv run pytest agent/tests/test_router.py -v -m integration -s


@pytest.mark.integration
class TestRouterIntegration:
    """실제 LLM API를 호출하는 통합 테스트. API 키가 필요합니다."""

    @pytest.mark.asyncio
    async def test_game_create_intent(self):
        result = await router(_state("불속성 검을 하나 만들어줘."))
        print(f"\n[게임_요소_생성] {result}")
        assert result["intent"] == "게임_요소_생성"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_game_modify_intent(self):
        result = await router(_state("게임 제목 을 냥냥펀치~!! 로 바꾸고싶어."))
        print(f"\n[게임_요소_수정] {result}")
        assert result["intent"] == "게임_요소_수정"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_game_query_intent(self):
        result = await router(_state("지금 게임 제목 뭐야?"))
        print(f"\n[게임_요소_조회] {result}")
        assert result["intent"] == "게임_요소_조회"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_clarification_needed_intent(self):
        result = await router(_state("천 갑옷은 얼마야?"))  # 대상/종류 전혀 없음
        print(f"\n[게임_요소_조회] {result}")
        assert result["intent"] == "게임_요소_조회"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_general_chat_intent(self):
        result = await router(_state("아바타 주인공 누구야?"))  # 게임과 무관한 일상 대화
        print(f"\n[일반_대화] {result}")
        assert result["intent"] == "일반_대화"
        assert "final_response" in result

    @pytest.mark.asyncio
    async def test_out_of_scope_intent(self):
        result = await router(
            _state(
                "드래곤볼 7개를 만들어서 그 드래곤볼을 다 모으면 용이 나타나는 효과가 나타나게 해줘"
            )
        )
        print(f"\n[범위_외] {result}")
        assert result["intent"] == "범위_외"
        assert "final_response" in result


# ── 현실적인 사용 시나리오 통합 테스트 ─────────────────────────────────────────
# 프롬프트 예시에 없는 실제 사용자 입력 패턴으로 의도 분류 검증


@pytest.mark.integration
class TestRouterIntegrationRealistic:
    """프롬프트 예시에 없는 현실적인 입력으로 의도 분류를 검증한다."""

    # ── 게임_요소_생성 ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "늑대인간 보스 몬스터 하나 추가해줘",
            "파티원 전체 HP 회복하는 포션 만들어줘",
            "독 속성 단검 넣어줘",
            "레벨 50짜리 드래곤 적 만들어줘",
            "상태이상 '혼란' 추가해줄 수 있어?",
        ],
    )
    async def test_create_intent(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[게임_요소_생성] '{user_input}' → {result['intent']}")
        assert result["intent"] == "게임_요소_생성", f"입력: {user_input!r}"
        assert result["confidence"] >= 0.7

    # ── 게임_요소_수정 ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "용사 초기 레벨 5로 높여줘",
            "고블린 경험치 드롭 30으로 낮춰줘",
            "마법사 직업 기본 MP 두 배로 올려줘",
            "불꽃검 공격력 너무 약한 것 같은데 올려줘",
            "오크 삭제해줘",
        ],
    )
    async def test_modify_intent(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[게임_요소_수정] '{user_input}' → {result['intent']}")
        assert result["intent"] == "게임_요소_수정", f"입력: {user_input!r}"
        assert result["confidence"] >= 0.7

    # ── 게임_요소_조회 ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "지금 만들어진 스킬 다 보여줘",
            "주인공 이름이 뭐야?용사 캐릭터 스탯 알려줘",
            "현재 등록된 직업 몇 개야?",
            "독검 데미지 공식이 뭐야?",
            "파티에 누가 있어?",
        ],
    )
    async def test_query_intent(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[게임_요소_조회] '{user_input}' → {result['intent']}")
        assert result["intent"] == "게임_요소_조회", f"입력: {user_input!r}"
        assert result["confidence"] >= 0.7

    # ── 추가_정보_필요 ──────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "몬스터 좀 어떻게 해줘",
            "강하게 해줘",
            "게임 좀 고쳐줘",
        ],
    )
    async def test_clarification_intent(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[추가_정보_필요] '{user_input}' → {result['intent']}")
        assert result["intent"] == "추가_정보_필요", f"입력: {user_input!r}"
        assert "final_response" in result

    # ── 복합_의도 ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "마법사 스탯 확인하고 MP 올려줘",
            "현재 아이템 목록 보고 제일 비싼 거 삭제해줘",
            "슬라임 HP 확인해보고 너무 낮으면 올려줘",
        ],
    )
    async def test_complex_intent(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[복합_의도] '{user_input}' → {result['intent']}")
        assert result["intent"] == "복합_의도", f"입력: {user_input!r}"

    # ── 일반_대화 ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "오늘 게임 개발 너무 힘드네",
            "잘 됐다 고마워",
            "잠깐 쉬고 올게",
            "배고파",
        ],
    )
    async def test_general_chat(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[일반_대화] '{user_input}' → {result['intent']}")
        assert result["intent"] == "일반_대화", f"입력: {user_input!r}"
        assert "final_response" in result

    # ── 범위_외 ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "user_input",
        [
            "전사 캐릭터 스프라이트 멋있게 바꿔줘",
            "전투 배경음악 웅장한 걸로 넣어줘",
            "마인크래프트처럼 블록 쌓기 시스템 넣어줘",
            "포켓몬 진화 시스템 구현해줘",
            "오늘 주식 시장 어떻게 돼?",
        ],
    )
    async def test_out_of_scope(self, user_input):
        result = await router(_state(user_input))
        print(f"\n[범위_외] '{user_input}' → {result['intent']}")
        assert result["intent"] == "범위_외", f"입력: {user_input!r}"
        assert "final_response" in result
