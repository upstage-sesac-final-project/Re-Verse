# Responder 노드 — 최종 응답 생성

> 담당: 세종
> 상태: 설계 문서 (미구현)
> 작성일: 2026-04-06
> 관련 문서: workflow_implementation.md, generation_api.md

---

## 개요

Responder는 Full Generation 워크플로우의 **마지막 노드**다.
역할:
1. 생성 성공/실패 상태 판별
2. 사용자에게 보낼 **한국어 결과 메시지** 작성
3. WebSocket으로 최종 진행률 100% 전송
4. `GenerationState`에 `final_message` 기록

```
validator ──► responder ──► [END]
```

Validator가 `"respond"` 라우트를 반환하면 항상 responder로 이동한다:
- 검증 통과 (성공)
- 재시도 한계 도달 (부분 실패)

---

## 입력: `GenerationState` 필드

Responder가 읽는 필드:

```python
state["game_spec"]          # GameSpec: 제목, 스토리, 캐릭터 목록
state["id_table"]           # IdTable: 생성된 에셋 수 계산용
state["map_specs"]          # list[MapSpec]: 맵 목록
state["validation_errors"]  # list[str]: 검증 오류 (비어있으면 성공)
state["retry_count"]        # int: 재시도 횟수
state["generation_id"]      # str: WebSocket 채널 ID
```

---

## 출력: `GenerationState` 업데이트

```python
{
    "final_message": str,   # 사용자에게 전달할 메시지 (한국어)
    "is_success": bool,     # True=성공, False=부분 실패
}
```

---

## `generation_responder` 구현

```python
# agent/generation/nodes/generation_responder.py

import logging
from agent.generation.state import GenerationState
from agent.generation.progress import publish_progress

logger = logging.getLogger(__name__)


async def generation_responder(state: GenerationState) -> dict:
    """
    워크플로우 최종 노드.
    성공 또는 재시도 한계 도달 후 사용자 메시지 생성.
    """
    errors     = state.get("validation_errors", [])
    game_spec  = state["game_spec"]
    id_table   = state["id_table"]
    map_specs  = state.get("map_specs", [])
    retry_cnt  = state.get("retry_count", 0)
    gen_id     = state["generation_id"]

    is_success = len(errors) == 0

    # 메시지 생성
    if is_success:
        message = _build_success_message(game_spec, id_table, map_specs)
    else:
        message = _build_partial_message(game_spec, errors, retry_cnt)

    logger.info(
        "generation_responder: gen_id=%s is_success=%s errors=%d",
        gen_id, is_success, len(errors),
    )

    # WebSocket 최종 진행률
    await publish_progress(gen_id, {
        "type": "completed" if is_success else "completed_with_warnings",
        "progress": 100,
        "message": message,
    })

    return {
        "final_message": message,
        "is_success": is_success,
    }
```

---

## 성공 메시지: `_build_success_message()`

```python
def _build_success_message(
    game_spec: GameSpec,
    id_table: IdTable,
    map_specs: list[MapSpec],
) -> str:
    """
    생성 완료 시 사용자에게 보여줄 요약 메시지 (한국어).
    """
    # 에셋 수 집계
    actor_count  = len(id_table.actors)
    map_count    = len(map_specs)
    item_count   = len(id_table.items) + len(id_table.weapons) + len(id_table.armors)
    enemy_count  = len(id_table.enemies)

    # 맵 타입별 분류
    town_maps    = [m for m in map_specs if m.map_type == "town"]
    dungeon_maps = [m for m in map_specs if m.map_type == "dungeon"]
    boss_maps    = [m for m in map_specs if m.map_type == "boss"]

    map_summary = []
    if town_maps:
        map_summary.append(f"마을 {len(town_maps)}개")
    if dungeon_maps:
        map_summary.append(f"던전 {len(dungeon_maps)}개")
    if boss_maps:
        map_summary.append(f"보스 맵 {len(boss_maps)}개")

    lines = [
        f"**{game_spec.title}** 게임이 생성되었습니다! 🎮",
        "",
        f"📖 {game_spec.story[:80]}{'...' if len(game_spec.story) > 80 else ''}",
        "",
        "## 생성된 콘텐츠",
        f"- 캐릭터: {actor_count}명",
        f"- 맵: {map_count}개 ({', '.join(map_summary)})",
        f"- 아이템/무기/방어구: {item_count}종",
        f"- 적 종류: {enemy_count}종",
        "",
        "RPG Maker MZ 에디터에서 바로 실행해보세요!",
    ]
    return "\n".join(lines)
```

**출력 예시:**
```
**중세 판타지의 전설** 게임이 생성되었습니다! 🎮

📖 마왕의 부활로 위기에 처한 왕국을 구하기 위해 용사가 여정을 떠난다...

## 생성된 콘텐츠
- 캐릭터: 3명
- 맵: 5개 (마을 2개, 던전 2개, 보스 맵 1개)
- 아이템/무기/방어구: 12종
- 적 종류: 6종

RPG Maker MZ 에디터에서 바로 실행해보세요!
```

---

## 부분 실패 메시지: `_build_partial_message()`

재시도 한계 도달 시 — 일부 검증 오류가 있지만 게임 파일은 저장된 상태.

```python
def _build_partial_message(
    game_spec: GameSpec,
    errors: list[str],
    retry_cnt: int,
) -> str:
    """
    부분 실패 시 사용자에게 보여줄 메시지.
    오류 목록 포함, 수동 확인 안내.
    """
    # 오류는 최대 5개만 표시 (너무 길면 가독성 저하)
    shown_errors = errors[:5]
    more_count   = len(errors) - 5 if len(errors) > 5 else 0

    error_lines = [f"  - {e}" for e in shown_errors]
    if more_count > 0:
        error_lines.append(f"  - ... 외 {more_count}개")

    lines = [
        f"**{game_spec.title}** 게임이 생성되었지만 일부 문제가 있습니다.",
        "",
        f"재시도 {retry_cnt}회 후에도 해결되지 않은 문제:",
        *error_lines,
        "",
        "게임 파일은 저장되었습니다. RPG Maker MZ에서 직접 확인하고 수정해주세요.",
    ]
    return "\n".join(lines)
```

**출력 예시:**
```
**중세 판타지의 전설** 게임이 생성되었지만 일부 문제가 있습니다.

재시도 2회 후에도 해결되지 않은 문제:
  - 보스 맵 '드래곤 성채'에 엔딩 이벤트(코드 353/354) 없음
  - 스위치 '드래곤_defeated'가 transfer 이벤트에서 참조되지 않음

게임 파일은 저장되었습니다. RPG Maker MZ에서 직접 확인하고 수정해주세요.
```

---

## `build_summary()` — DB 저장용 요약

워크플로우 완료 후 `generation_api.py`에서 DB에 저장하는 요약:

```python
# app/backend/services/generation_service.py

def build_summary(final_state: GenerationState) -> str:
    """
    Generation 레코드의 result_summary 필드 (DB 저장).
    사용자 메시지보다 간결한 기계 친화적 요약.
    """
    game_spec  = final_state.get("game_spec")
    map_specs  = final_state.get("map_specs", [])
    id_table   = final_state.get("id_table")
    errors     = final_state.get("validation_errors", [])

    return json.dumps({
        "title":       game_spec.title if game_spec else "unknown",
        "map_count":   len(map_specs),
        "actor_count": len(id_table.actors) if id_table else 0,
        "error_count": len(errors),
        "is_success":  len(errors) == 0,
    }, ensure_ascii=False)
```

---

## WebSocket 이벤트 타입 요약

Responder가 전송하는 마지막 WebSocket 메시지:

| is_success | type | progress | 의미 |
|-----------|------|----------|------|
| True | `"completed"` | 100 | 완전 성공 |
| False | `"completed_with_warnings"` | 100 | 부분 실패, 파일은 저장됨 |

프론트엔드는 `type="completed"` 또는 `type="completed_with_warnings"` 수신 시
생성 완료 UI를 표시하고 다운로드 링크를 활성화한다.

---

## `GenerationState` 최종 필드 (워크플로우 종료 시점)

```python
class GenerationState(TypedDict):
    # 입력
    user_input:         str
    game_id:            str
    generation_id:      str

    # B. 설계사 출력
    generation_order:   list[str]           # 에셋 생성 순서

    # C. 에셋 생성 출력
    game_spec:          GameSpec
    id_table:           IdTable
    switch_table:       SwitchTable
    generated_assets:   dict[str, Any]      # {"Actors.json": [...], ...}

    # D+E. 맵 설계사 + 타일 생성기 출력
    map_specs:          list[MapSpec]
    map_tiles:          dict[int, list[int]] # map_id → flat 1D array (width×height×6)
    connection_info:    dict[int, Any]       # map_id → MapConnectionInfo

    # F+G. 이벤트 기획자 + 컴파일러 출력
    event_dsl:          dict[int, list]      # map_id → DSL 이벤트
    compiled_events:    dict[int, list[dict]]

    # H. 통합기 출력
    final_project:      dict[str, Any]       # 파일명 → 최종 JSON

    # 검증/재시도
    validation_passed:  bool
    validation_errors:  list[str]
    validation_warnings: list[str]
    retry_count:        int

    # 체크포인트
    completed_phases:   list[str]
    error_phase:        str | None
    error_message:      str | None

    # 최종 출력 (responder가 채움)
    final_message:      str
    is_success:         bool
```

---

## 리스크

### R-R1: `final_message`가 너무 길어서 WebSocket 전송 실패 (P3)

메시지가 수백 KB가 되는 경우는 없지만, 오류가 많을 때 부분 실패 메시지가 길어질 수 있다.

**완화**: `shown_errors = errors[:5]` (최대 5개 표시) + 나머지 카운트 표기.

### R-R2: `game_spec`이 None인 경우 (P2)

game_designer 노드 실패 시 `game_spec`이 None. `build_summary()`와 `_build_success_message()`가 AttributeError.

**완화**:
```python
title = game_spec.title if game_spec else "알 수 없는 게임"
```

### R-R3: WebSocket 채널이 닫힌 상태에서 `publish_progress()` 호출 (P2)

사용자가 페이지를 떠난 경우. `publish_progress()`가 예외를 발생시킬 수 있음.

**완화**: `publish_progress()`를 try/except로 감싸고 예외를 무시 (메시지는 DB에 저장되므로 손실 없음):
```python
try:
    await publish_progress(gen_id, {...})
except Exception:
    logger.warning("WebSocket 전송 실패 (채널 닫힘): gen_id=%s", gen_id)
```

---

## 테스트

```python
# agent/tests/generation/test_responder.py

def test_success_message_contains_title(mock_state):
    mock_state["validation_errors"] = []
    mock_state["game_spec"].title = "테스트 게임"
    result = _build_success_message(
        mock_state["game_spec"],
        mock_state["id_table"],
        mock_state["map_specs"],
    )
    assert "테스트 게임" in result

def test_partial_message_shows_errors(mock_state):
    errors = ["오류1", "오류2"]
    result = _build_partial_message(mock_state["game_spec"], errors, retry_cnt=2)
    assert "오류1" in result
    assert "재시도 2회" in result

def test_partial_message_limits_to_5_errors():
    errors = [f"오류{i}" for i in range(10)]
    result = _build_partial_message(MagicMock(title="x"), errors, retry_cnt=1)
    assert "외 5개" in result

async def test_responder_publishes_progress(mock_state, mock_publish):
    mock_state["validation_errors"] = []
    await generation_responder(mock_state)
    mock_publish.assert_called_once()
    call_args = mock_publish.call_args[0][1]
    assert call_args["type"] == "completed"
    assert call_args["progress"] == 100

async def test_responder_sets_is_success_false_on_errors(mock_state):
    mock_state["validation_errors"] = ["오류"]
    result = await generation_responder(mock_state)
    assert result["is_success"] is False

def test_build_summary_json_parseable(mock_state):
    summary = build_summary(mock_state)
    parsed = json.loads(summary)
    assert "title" in parsed
    assert "is_success" in parsed
```
