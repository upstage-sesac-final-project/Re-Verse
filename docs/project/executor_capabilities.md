# Executor(4단계) 기능 매트릭스

구조화 `execution_plan`이 `_is_structured_execution_plan`을 통과하면 `agent/graph/nodes/executor.py`의 MCP 우선 → 실패 시 레거시 폴백 경로로 실행된다.

## 공통

| 구분 | 설명 |
|------|------|
| MCP | `MCP_ENABLED` 및 stdio 서버 설정이 유효할 때 `MCP_TOOL_MAP`에 있는 `(target_file, action)`만 Node MCP `call_tool` 시도 |
| 폴백 | MCP 실패 시 `_supports_legacy_fallback`에 있는 조합만 Python 매니저로 재시도; 없으면 `MCP_ABORT_NO_FALLBACK` |
| 로깅 | Planner 성공 직후·Executor 진입 직후 `execution_plan` 전체 JSON이 INFO로 출력(길면 잘림) |

## `action_type` 정규화 (`_normalize_structured_action`)

| 대상 | 플래너 입력 | 정규화 결과 |
|------|-------------|-------------|
| Actors.json | `query` + `actor_id` / `actorId` | `query_by_id` |
| Actors.json | `query` + `list_actors` / `list_all_actors` / `scope=all_actors` | `list` |
| Actors.json | `query` + `searchTerm`/`search_term`/`query`(문자열) 있고 `actor_name`/`name` 없음 | `search` |
| Actors.json | `update` + `updates` + `actor_id`/`actorId` | `update_actor` |
| Actors.json | `update` + **class_name / class_id 없음** (이름 변경·일반 필드) | `update_actor` |
| Actors.json | (실행 전) `actor_name`/`old_name` 있으면 `Actors.json`에서 id 조회해 **잘못된 actor_id 보정** | — |
| Items.json / Enemies.json | `query` | `search` |
| System.json | `update` + 세부 필드 | `update_game_title`, `set_variable_name`, `set_switch_name`, `update_starting_position` 등 |

플래너 스키마에서는 `list` / `search`를 `action_type`으로 직접 줄 수 있다.

## 파일별 요약

### Actors.json

| action (정규화 후) | MCP 툴 | MCP off / 실패 시 레거시 |
|--------------------|--------|---------------------------|
| list | `get_actors` | `ActorManager` `list` |
| search | `search_actors` | `ActorManager` `search` |
| query_by_id | `get_actor` | `ActorManager` `query_by_id` |
| query | — | `ActorManager` `query` (이름) |
| create | `create_actor` | `ActorManager` `create` |
| update | — | `ActorManager` `update_class` (**class_name 또는 class_id**가 있을 때만) |
| update_actor | `update_actor` | `ActorManager` `update_general` (이름·별명 등) |

### Classes.json

| action | MCP | 레거시 |
|--------|-----|--------|
| query / create / update | 없음 | `ClassManager` |

### System.json

| action | MCP | 레거시 |
|--------|-----|--------|
| query, list_variables, list_switches, get_game_title | 일부 | 환경에 따라 다름 |
| update_game_title, set_variable_name, set_switch_name, update_starting_position | 해당 툴 | 대응 매니저 분기 |
| update (party 등) | — | `SystemManager` 등 |

### Skills.json

| action | MCP | 레거시 |
|--------|-----|--------|
| list, search, query, create*, update | 매핑 있음 | `create`·`*_skill`·`update` 등 분기 |

### Items.json / Enemies.json

| action | MCP | 레거시 |
|--------|-----|--------|
| list, search | MCP 있음 | `search`·CRUD는 매니저 |

### Weapons.json / Armors.json

| action | MCP | 레거시 |
|--------|-----|--------|
| list | `get_weapons` / `get_armors` | 매핑 없으면 레거시 없음 |

---

세부 분기는 `executor.py`의 `MCP_TOOL_MAP`, `_execute_one_structured_step`, 각 `*Manager` 구현을 기준으로 한다.
