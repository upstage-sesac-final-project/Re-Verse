"""Router 노드 단위 테스트.

실행 방법:
    # 단위 테스트만 (LLM 호출 없음, 빠름)
    uv run pytest agent/tests/test_router.py -v

    # 실제 LLM 호출 포함 (API 키 필요)
    uv run pytest agent/tests/test_router.py -v -m integration -s
"""

from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.router import _ParsedCommand, _RouterOutput, router
from agent.editor.prompts.router_prompt import build_prompt
from agent.editor.state import AgentState

# ── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _mock_output(
    intent: str,
    confidence: float = 0.9,
    reasoning: str = "test",
    response: str = "",
    *,
    field: str = "",
    target: str = "",
    action: str = "",
    property: str = "",
    value: str = "",
    bulk_scope: str = "",
) -> _RouterOutput:
    return _RouterOutput(
        intent=intent,  # type: ignore[arg-type]
        confidence=confidence,
        reasoning=reasoning,
        response=response,
        parsed_command=_ParsedCommand(
            field=field,
            target=target,
            action=action,
            property=property,
            value=value,
            bulk_scope=bulk_scope,
        ),
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
    @pytest.mark.parametrize(
        "intent",
        ["object_create", "object_update", "event_create", "event_update", "query", "game_overview"],
    )
    async def test_action_intents_return_intent_and_confidence(self, intent):
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(intent, confidence=0.95)
            result = await router(_state("테스트 입력"))

        assert result["intent"] == intent
        assert result["confidence"] == 0.95
        assert "final_response" not in result  # 액션 인텐트는 즉시 응답 없음

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "intent",
        ["clarification_needed", "small_talk", "out_of_scope"],
    )
    async def test_terminal_intents_set_final_response(self, intent):
        expected_response = "이것은 응답입니다."
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(intent, response=expected_response)
            result = await router(_state("테스트 입력"))

        assert result["intent"] == intent
        assert result["final_response"] == expected_response

    @pytest.mark.asyncio
    async def test_passes_correct_structured_output_type(self):
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output("object_create")
            await router(_state("새 적 만들어줘"))

        _, kwargs = mock_llm.call_args
        assert kwargs.get("structured_output") is _RouterOutput

    @pytest.mark.asyncio
    async def test_conversation_history_forwarded_to_prompt(self):
        history = [{"role": "user", "content": "이전 대화"}]
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output("query")
            await router(_state("현재 적 목록 보여줘", history=history))

        messages = mock_llm.call_args[0][0]
        assert any("이전 대화" in str(m.content) for m in messages)

    @pytest.mark.asyncio
    async def test_parsed_command_propagated_to_state(self):
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(
                "object_create", field="적", target="슬라임", action="생성"
            )
            result = await router(_state("적 슬라임 만들어줘"))

        assert result["parsed_command"] == {
            "field": "적",
            "target": "슬라임",
            "action": "생성",
            "property": "",
            "value": "",
            "bulk_scope": "",
        }

    @pytest.mark.asyncio
    async def test_parsed_command_extended_fields_propagated(self):
        """property/value/bulk_scope 가 state 에 전파되어야 한다 (Phase D-followup)."""
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(
                "object_update",
                field="적",
                target="슬라임",
                action="수정",
                property="HP",
                value="200",
            )
            result = await router(_state("슬라임 HP 를 200 으로 올려줘"))

        assert result["parsed_command"]["property"] == "HP"
        assert result["parsed_command"]["value"] == "200"
        assert result["parsed_command"]["bulk_scope"] == ""

    @pytest.mark.asyncio
    async def test_parsed_command_bulk_scope(self):
        """bulk_scope='all' 이 state 에 전파되어야 한다."""
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output(
                "object_update",
                field="적",
                target="",
                action="수정",
                property="HP",
                value="2배",
                bulk_scope="all",
            )
            result = await router(_state("모든 적 HP 두 배로 올려"))

        assert result["parsed_command"]["bulk_scope"] == "all"
        assert result["parsed_command"]["property"] == "HP"

    @pytest.mark.asyncio
    async def test_empty_input_returns_clarification_without_llm(self):
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            result = await router(_state("   "))

        assert mock_llm.await_count == 0
        assert result["intent"] == "clarification_needed"
        assert "final_response" in result

    @pytest.mark.asyncio
    async def test_low_confidence_action_force_clarification(self):
        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = _mock_output("object_create", confidence=0.4)
            result = await router(_state("적 어떻게 해줘"))

        assert result["intent"] == "clarification_needed"

    @pytest.mark.asyncio
    async def test_pending_resume_yes_path(self):
        """active hold 가 있고 yes 판정이면 pending_resumed=True + snapshot 전달."""
        from agent.editor.pending_store import PendingStore

        store = PendingStore()
        store.set(
            "conv-1",
            hold_reason="not_found",
            hold_question="'검 A' 가 없는데 만들까요?",
            snapshot={"field": "무기", "target": "검 A"},
        )

        s = _state("어 그래")
        s["conversation_id"] = "conv-1"

        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            # 첫 호출: yes/no 판정 (is_answer=True)
            # 두 번째 호출: 메인 분류
            from agent.editor.nodes.router import _YesNoOutput

            mock_llm.side_effect = [
                _YesNoOutput(is_answer=True, reasoning="긍정 응답"),
                _mock_output("object_create", field="무기", target="검 A", action="생성"),
            ]
            result = await router(s, store=store)

        assert result["pending_resumed"] is True
        assert result["resumed_snapshot"] == {"field": "무기", "target": "검 A"}
        entry = store.get("conv-1")
        assert entry is not None
        assert entry.status == "resolved"

    @pytest.mark.asyncio
    async def test_pending_resume_no_path_drops(self):
        """active hold 가 있지만 no 판정이면 pending 은 dropped + 새 intent 진행."""
        from agent.editor.pending_store import PendingStore

        store = PendingStore()
        store.set(
            "conv-2",
            hold_reason="not_found",
            hold_question="'검 A' 가 없는데 만들까요?",
            snapshot={"field": "무기", "target": "검 A"},
        )

        s = _state("아니 됐고 슬라임 만들어줘")
        s["conversation_id"] = "conv-2"

        with patch("agent.editor.nodes.router.invoke_llm", new_callable=AsyncMock) as mock_llm:
            from agent.editor.nodes.router import _YesNoOutput

            mock_llm.side_effect = [
                _YesNoOutput(is_answer=False, reasoning="새 요청"),
                _mock_output("object_create", field="적", target="슬라임", action="생성"),
            ]
            result = await router(s, store=store)

        assert result["pending_resumed"] is False
        assert "resumed_snapshot" not in result
        entry = store.get("conv-2")
        assert entry is not None
        assert entry.status == "dropped"


# ── 통합 테스트 (실제 LLM 호출) ───────────────────────────────────────────────
# 실행: uv run pytest agent/tests/test_router.py -v -m integration -s


@pytest.mark.integration
class TestRouterIntegration:
    """실제 LLM API를 호출하는 통합 테스트. API 키가 필요합니다."""

    @pytest.mark.asyncio
    async def test_game_create_intent(self):
        result = await router(_state("불속성 검을 하나 만들어줘."))
        print(f"\n[object_create] {result}")
        assert result["intent"] == "object_create"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_game_modify_intent(self):
        result = await router(_state("게임 제목 을 냥냥펀치~!! 로 바꾸고싶어."))
        print(f"\n[object_update] {result}")
        assert result["intent"] == "object_update"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_game_query_intent(self):
        result = await router(_state("지금 게임 제목 뭐야?"))
        print(f"\n[query] {result}")
        assert result["intent"] == "query"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_clarification_needed_intent(self):
        result = await router(_state("천 갑옷은 얼마야?"))  # 대상/종류 전혀 없음
        print(f"\n[query] {result}")
        assert result["intent"] == "query"
        assert result["confidence"] >= 0.7

    @pytest.mark.asyncio
    async def test_general_chat_intent(self):
        result = await router(_state("아바타 주인공 누구야?"))  # 게임과 무관한 일상 대화
        print(f"\n[small_talk] {result}")
        assert result["intent"] == "small_talk"
        assert "final_response" in result

    @pytest.mark.asyncio
    async def test_out_of_scope_intent(self):
        result = await router(
            _state(
                "드래곤볼 7개를 만들어서 그 드래곤볼을 다 모으면 용이 나타나는 효과가 나타나게 해줘"
            )
        )
        print(f"\n[out_of_scope] {result}")
        assert result["intent"] == "out_of_scope"
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
        print(f"\n[object_create] '{user_input}' → {result['intent']}")
        assert result["intent"] == "object_create", f"입력: {user_input!r}"
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
        print(f"\n[object_update] '{user_input}' → {result['intent']}")
        assert result["intent"] == "object_update", f"입력: {user_input!r}"
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
        print(f"\n[query] '{user_input}' → {result['intent']}")
        # game_overview 가 살짝 섞일 수 있음 ("주인공 이름 뭐야?" 등은 경계 케이스)
        assert result["intent"] in {"query", "game_overview"}, f"입력: {user_input!r}"
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
        print(f"\n[clarification_needed] '{user_input}' → {result['intent']}")
        assert result["intent"] == "clarification_needed", f"입력: {user_input!r}"
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
        print(f"\n[multi_intent] '{user_input}' → {result['intent']}")
        assert result["intent"] == "multi_intent", f"입력: {user_input!r}"

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
        print(f"\n[small_talk] '{user_input}' → {result['intent']}")
        assert result["intent"] == "small_talk", f"입력: {user_input!r}"
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
        print(f"\n[out_of_scope] '{user_input}' → {result['intent']}")
        assert result["intent"] in {"out_of_scope", "small_talk"}, f"입력: {user_input!r}"
        assert "final_response" in result
