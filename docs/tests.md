# agent/tests — 테스트 가이드

Re-Verse 에이전트 레이어 테스트의 위치·목적·실행법 정리.

## 폴더 구조

```
agent/tests/
  conftest.py                     공통 pytest fixture (base_game → tmp STORAGE_PATH 복사)
  test_repl.py                    로컬 대화형 REPL 러너 (pytest 비수집, CLI 실행)
  test_game_data_io.py            game_data_io 순수 로직 단위 테스트
  test_game_paths.py              game_paths.ensure_rpgmaker_mz_project_shell 테스트
  editor/                         agent/editor 하위 노드·MCP 테스트
  generation/                     agent/generation 파이프라인 테스트
```

---

## 루트 (`agent/tests/`)

| 파일 | 목적 | 실행 |
|---|---|---|
| `conftest.py` | pytest fixture. `STORAGE_PATH` 가 tmp_path 일 때 `base_game/data/` 를 `game_001/data/` 로 복사. editor/ · generation/ 모두 상속. | — (암묵적) |
| `test_repl.py` | editor workflow를 실제 LLM 으로 돌리는 대화형 REPL. 수동 디버깅용. | `uv run python -m agent.tests.test_repl [--game-id game_001]` |
| `test_game_data_io.py` | `read_game_json` / `write_game_json` 등 I/O 로직 검증. LLM·외부 호출 없음. | `uv run pytest agent/tests/test_game_data_io.py` |
| `test_game_paths.py` | 프로젝트 루트 보강 로직 (`ensure_rpgmaker_mz_project_shell`). | `uv run pytest agent/tests/test_game_paths.py` |

---

## `editor/` — Editor 노드·MCP 테스트

LLM 을 타는 editor 노드 + MCP 연동 테스트. 비-LLM 노드 (planner / executor 의 deterministic 부분) 테스트는 의도적으로 제거됨.

| 파일 | 목적 | 실행 |
|---|---|---|
| `test_router.py` | Router 노드 의도 분류 테스트 (LLM). | `uv run pytest agent/tests/editor/test_router.py` |
| `test_definition.py` | Definition 노드 Step 1~10 파이프라인 인터랙티브 실행. | `uv run python -m agent.tests.editor.test_definition` |
| `test_reader.py` | Reader 노드(엔티티 매칭) 인터랙티브 실행. | `uv run python -m agent.tests.editor.test_reader` |
| `test_synthesizer.py` | Synthesizer 노드 단위 테스트 (LLM 응답 포맷 검증). | `uv run pytest agent/tests/editor/test_synthesizer.py` |
| `test_synthesizer_prompt.py` | `synthesizer_prompt` 스냅샷 diff 함수 순수 로직 테스트 (LLM 호출 없음). | `uv run pytest agent/tests/editor/test_synthesizer_prompt.py` |
| `test_full.py` | 1~6 노드 전체 E2E 통합 실행 (No-Pytest 스크립트). | `uv run python -m agent.tests.editor.test_full` |
| `test_pipeline.py` | 전체 노드 파이프라인 pytest 통합 테스트 (LLM 호출). | `uv run pytest agent/tests/editor/test_pipeline.py` |
| `test_mcp.py` | `mcp_toolbox` 순수 함수 + `resolve_mcp_server_key` 우선순위 단위 테스트 (외부 호출 없음). | `uv run pytest agent/tests/editor/test_mcp.py` |
| `check_mcp_smoke.py` | 컨테이너/EC2 에서 MCP stdio 연결 확인용 수동 smoke. | `uv run python -m agent.tests.editor.check_mcp_smoke` |
| `check_tools.py` | MCP 서버가 제공하는 tool 목록 덤프 수동 스크립트. | `uv run python -m agent.tests.editor.check_tools` |

---

## `generation/` — Generation 파이프라인 테스트

`agent/generation/` 의 맵·에셋·밸런스 파이프라인 테스트.

| 파일 | 목적 | 실행 |
|---|---|---|
| `test_integrator.py` | `integrator.py` 유닛 테스트. Map*.json / System.json 조립 검증. | `uv run pytest agent/tests/generation/test_integrator.py` |
| `test_balance.py` | `balance.py` 유닛 테스트. RPG Maker MZ 공식(ATK*4 - DEF*2) 기반 밸런스. | `uv run pytest agent/tests/generation/test_balance.py` |
| `test_event_compiler.py` | `EventCompiler` 6개 DSL 타입 컴파일 검증. | `uv run pytest agent/tests/generation/test_event_compiler.py` |
| `test_generation_validator.py` | `generation_validator.py` 핵심 검증 함수 개별 테스트. | `uv run pytest agent/tests/generation/test_generation_validator.py` |
| `test_generation_foundations.py` | `game_designer` / `asset_planner` / `progress` 연계 통합 테스트. | `uv run pytest agent/tests/generation/test_generation_foundations.py` |
| `test_intent.py` | mapgen intent extractor 통합 테스트 (쿼리 → MapIntent 구조화 출력). | `uv run pytest agent/tests/generation/test_intent.py` |
| `test_scores.py` | mapgen 샘플맵 점수 분포·필터/랭킹 로직 검증. | `uv run pytest agent/tests/generation/test_scores.py` |

---

## 전체 실행

```bash
# 전체 agent 테스트 (deterministic)
uv run pytest agent/tests

# editor 만
uv run pytest agent/tests/editor

# generation 만
uv run pytest agent/tests/generation

# LLM 의존 테스트 제외 (빠른 CI 용)
uv run pytest agent/tests --ignore=agent/tests/editor/test_router.py \
  --ignore=agent/tests/editor/test_pipeline.py \
  --ignore=agent/tests/editor/test_full.py
```

### pytest 관련 주의
- `test_full.py`, `test_definition.py`, `test_reader.py` 는 **pytest 미수집** (module level 실행 스크립트). `python -m` 으로 실행.
- `check_*.py` 는 `check_` prefix 라 pytest 미수집. 수동 실행 전용.
- LLM 호출 테스트는 `.env` 의 `LLM_API_KEY` + `LLM_MODEL` 세팅이 되어 있어야 통과.
- MCP 연동 smoke (`check_mcp_smoke.py`) 는 `MCP_ENABLED=true` + `MCP_NODE_SERVER_PATH` 필요.

### coverage
- `pyproject.toml` 의 `[tool.coverage.run] omit` 에서 `*/check_*.py` 는 수동 스크립트라 제외됨.
