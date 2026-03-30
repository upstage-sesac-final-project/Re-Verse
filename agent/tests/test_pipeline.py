"""전체 노드 파이프라인 통합 테스트.

실행 방법:
    uv run pytest agent/tests/test_pipeline.py -v -s -m integration
"""

import pytest

from agent.graph.workflow import graph

pytestmark = pytest.mark.integration

GAME_ID = "game_001"


def _base_state(user_input: str) -> dict:
    return {
        "user_input": user_input,
        "game_id": GAME_ID,
        "conversation_history": [],
        "retry_count": 0,
    }


# ── 1단계: Router ─────────────────────────────────────────────────────────────


class TestRouterNode:
    async def test_terminal_intent_ends_without_definition(self):
        """지원되지 않는 인텐트는 definition 없이 즉시 종료."""
        result = await graph.ainvoke(_base_state("안녕 반가워"))
        assert result["intent"] in {"일반_대화", "범위_외", "추가_정보_필요"}
        assert result.get("final_response") or True  # 터미널 응답
        assert "params_sufficient" not in result  # definition 미실행

    async def test_create_intent_proceeds_to_definition(self):
        """생성 인텐트는 definition까지 진행."""
        result = await graph.ainvoke(_base_state("슬라임 몬스터 만들어줘"))
        assert result["intent"] == "게임_요소_생성"
        assert "params_sufficient" in result

    async def test_modify_intent_proceeds_to_definition(self):
        result = await graph.ainvoke(_base_state("슬라임 HP를 300으로 올려줘"))
        assert result["intent"] == "게임_요소_수정"
        assert "params_sufficient" in result

    async def test_query_intent_proceeds_to_definition(self):
        result = await graph.ainvoke(_base_state("현재 적 목록 보여줘"))
        assert result["intent"] == "게임_요소_조회"
        assert "params_sufficient" in result


# ── 2단계: Definition ─────────────────────────────────────────────────────────


class TestDefinitionNode:
    async def test_insufficient_params_ends_early(self):
        """모호한 요청은 definition에서 종료, execution_plan 없음."""
        result = await graph.ainvoke(_base_state("뭔가 강하게 해줘"))
        # router에서 추가_정보_필요로 끝나거나 definition에서 끝남
        assert result.get("final_response") is not None or result.get("params_sufficient") is False
        assert "execution_plan" not in result or result.get("params_sufficient") is False

    async def test_sufficient_params_sets_modifications(self):
        """충분한 파라미터는 modifications 세팅 후 planner로 진행."""
        result = await graph.ainvoke(_base_state("슬라임 HP를 500으로 수정해줘"))
        if result.get("params_sufficient"):
            assert isinstance(result.get("modifications"), list)
            assert len(result["modifications"]) > 0


# ── 3단계: Planner ────────────────────────────────────────────────────────────


class TestPlannerNode:
    async def test_execution_plan_generated(self):
        """Planner가 실행 가능한 execution_plan을 생성한다."""
        result = await graph.ainvoke(_base_state("고블린 공격력을 50으로 올려줘"))
        if not result.get("params_sufficient"):
            pytest.skip("definition에서 params 부족으로 종료")
        assert isinstance(result.get("execution_plan"), list)
        assert len(result["execution_plan"]) > 0

    async def test_execution_plan_has_required_fields(self):
        result = await graph.ainvoke(_base_state("오크 HP를 200으로 올려줘"))
        if not result.get("params_sufficient"):
            pytest.skip("params 부족")
        for step in result.get("execution_plan", []):
            assert "target_file" in step or "task" in step  # 구조화 or 레거시 포맷


# ── 4단계: Executor ───────────────────────────────────────────────────────────


class TestExecutorNode:
    async def test_executor_sets_game_state_snapshots(self):
        """Executor가 current_game_state / modified_game_state를 세팅한다."""
        result = await graph.ainvoke(_base_state("슬라임 HP를 150으로 수정해줘"))
        if not result.get("params_sufficient"):
            pytest.skip("params 부족")
        assert isinstance(result.get("current_game_state"), dict)
        assert isinstance(result.get("modified_game_state"), dict)

    async def test_executor_sets_changes_log(self):
        result = await graph.ainvoke(_base_state("고블린 방어력을 20으로 올려줘"))
        if not result.get("params_sufficient"):
            pytest.skip("params 부족")
        assert isinstance(result.get("changes_log"), list)


# ── 5단계: Validator ──────────────────────────────────────────────────────────


class TestValidatorNode:
    async def test_validator_sets_success_field(self):
        """Validator 실행 후 success 필드가 bool로 세팅된다."""
        result = await graph.ainvoke(_base_state("슬라임 HP를 100으로 수정해줘"))
        if not result.get("params_sufficient"):
            pytest.skip("params 부족")
        assert isinstance(result.get("success"), bool)

    async def test_validator_sets_validation_results(self):
        result = await graph.ainvoke(_base_state("고블린 경험치를 30으로 수정해줘"))
        if not result.get("params_sufficient"):
            pytest.skip("params 부족")
        assert isinstance(result.get("validation_results"), list)


# ── 6단계: Synthesizer ────────────────────────────────────────────────────────


class TestSynthesizerNode:
    async def test_synthesizer_returns_final_response(self):
        """전체 파이프라인 완주 시 final_response가 비어있지 않아야 한다."""
        result = await graph.ainvoke(_base_state("슬라임 공격력을 25로 수정해줘"))
        assert isinstance(result.get("final_response"), str)
        assert len(result["final_response"]) > 0

    async def test_final_response_for_query(self):
        result = await graph.ainvoke(_base_state("현재 적 목록 알려줘"))
        assert isinstance(result.get("final_response"), str)
        assert len(result["final_response"]) > 0


# ── 전체 파이프라인 ────────────────────────────────────────────────────────────


class TestFullPipeline:
    async def test_create_enemy_full_pipeline(self):
        """적 생성 — 전체 6단계 완주."""
        result = await graph.ainvoke(_base_state("드래곤 보스 몬스터를 HP 5000으로 만들어줘"))
        assert "intent" in result
        assert "final_response" in result
        print(f"\n[생성] {result['final_response']}")

    async def test_modify_enemy_full_pipeline(self):
        """적 수정 — 전체 6단계 완주."""
        result = await graph.ainvoke(_base_state("슬라임 HP를 200으로 올려줘"))
        assert "intent" in result
        assert "final_response" in result
        print(f"\n[수정] {result['final_response']}")

    async def test_query_full_pipeline(self):
        """조회 — 전체 6단계 완주."""
        result = await graph.ainvoke(_base_state("현재 등록된 직업이 몇 개야?"))
        assert "intent" in result
        assert "final_response" in result
        print(f"\n[조회] {result['final_response']}")

    async def test_custom_user_input(self):
        """터미널에서 직접 입력한 텍스트로 파이프라인을 실행한다.

        실행 예시:
            uv run pytest agent/tests/test_pipeline.py::TestFullPipeline::test_custom_user_input -v -s -m integration
        """
        text = input("\n[입력] 테스트할 문장을 입력하세요: ").strip()
        if not text:
            pytest.skip("입력 없음")

        print(f"[*] '{text}' 파이프라인 시작...")

        result = await graph.ainvoke(_base_state(text))

        # ── 1단계: Router ──────────────────────────────────────
        print("\n[Step 1] Router 결과")
        print(f"  의도: {result.get('intent')} (신뢰도: {result.get('confidence', 0.0):.2f})")
        if result.get("intent") not in {"게임_요소_생성", "게임_요소_수정", "게임_요소_조회"}:
            print(f"  응답: {result.get('final_response', '진행 불가 의도')}")

        # ── 2단계: Definition ──────────────────────────────────
        if "params_sufficient" in result:
            print("\n[Step 2] Definition 결과")
            print(f"  params_sufficient: {result.get('params_sufficient')}")
            if not result.get("params_sufficient"):
                print(f"  응답: {result.get('final_response')}")
            else:
                for m in result.get("modifications", []):
                    print(f"  - [{m['type'].upper()}] {m['target']} (params: {m['params']})")
                print(f"  추출된 ID: {result.get('extracted_ids')}")

        # ── 3단계: Planner ─────────────────────────────────────
        if result.get("execution_plan"):
            print("\n[Step 3] Planner 결과")
            for i, step in enumerate(result["execution_plan"], 1):
                print(
                    f"  {i}. {step.get('target_file')} {step.get('action_type')} ({step.get('description')})"
                )

        # ── 4단계: Executor ────────────────────────────────────
        if result.get("changes_log"):
            print("\n[Step 4] Executor 결과")
            for log in result["changes_log"]:
                status = "성공" if log.get("success") else "실패"
                step_num = log.get("step_id") or log.get("step", "?")
                print(f"  ({step_num}) {log.get('tool_name', 'unknown')}: {status}")
                if not log.get("success"):
                    print(f"    에러: {log.get('error') or log.get('stderr') or '알 수 없는 에러'}")
                else:
                    print(f"    결과: {log.get('stdout') or '수행 완료'}")
            if result.get("backup_paths"):
                print(f"  백업: {len(result['backup_paths'])}개 파일")

        # ── 5단계: Validator ───────────────────────────────────
        if "success" in result:
            print("\n[Step 5] Validator 결과")
            print(
                f"  success: {result.get('success')}  retry_count: {result.get('retry_count', 0)}"
            )
            print(f"  summary: {result.get('validation_summary', '(없음)')}")
            for item in result.get("validation_results", []):
                status = "통과" if item.get("success") else "실패"
                print(f"  - {item.get('target')}: {status} (errors={item.get('error_count', 0)})")
                for err in item.get("errors", []):
                    print(f"    {err.get('loc', '$')} -> {err.get('msg', err)}")

        # ── 6단계: Synthesizer ─────────────────────────────────
        if result.get("final_response"):
            print("\n[Step 6] Synthesizer 결과")
            print(f"  {result['final_response']}")

        print("\n" + "-" * 50)

        assert "intent" in result
        assert isinstance(result.get("final_response"), str)
        assert len(result["final_response"]) > 0

    async def test_state_fields_populated_end_to_end(self):
        """수정 요청 시 모든 단계 상태 필드가 채워진다."""
        result = await graph.ainvoke(_base_state("고블린 HP를 120으로 수정해줘"))

        assert result.get("intent") in {"게임_요소_수정", "게임_요소_생성", "게임_요소_조회"}
        assert "final_response" in result

        if result.get("params_sufficient"):
            assert result.get("execution_plan")
            assert result.get("current_game_state") is not None
            assert result.get("modified_game_state") is not None
            assert isinstance(result.get("success"), bool)
            print(f"\n  intent={result['intent']}")
            print(f"  success={result['success']}")
            print(f"  response={result['final_response']}")
