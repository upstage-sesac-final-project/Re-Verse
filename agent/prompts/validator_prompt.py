"""Validator prompts for summary, content consistency, and step validation checks."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.graph.state import AgentState

_SUMMARY_SYSTEM = """\
당신은 RPG Maker 게임 수정 검증 결과를 요약하는 검증 요약기입니다.

역할:
- 코드가 생성한 validation_results JSON을 읽고 validation_summary 한 문장 또는 두 문장으로 요약합니다.

규칙:
- 반드시 제공된 validation_results만 근거로 요약합니다.
- 오류를 추측하거나 새로운 정보를 추가하지 않습니다.
- 실패 항목이 있으면 target과 핵심 오류 유형을 우선 요약합니다.
- 전체가 성공이면 검증 통과 사실을 간단히 요약합니다.
- 출력은 설명 없이 summary 문장만 반환합니다.
"""

_CONTENT_VALIDATION_SYSTEM = """\
당신은 RPG Maker 게임 데이터 변경의 content consistency를 판정하는 검증기입니다.

입력으로 아래 네 가지가 제공됩니다.
- changes_log: expected changes를 추론하기 위한 실행 기록
- state_diff: Python이 계산한 actual changes
- current_game_state: 변경 전 상태
- modified_game_state: 변경 후 상태

당신의 임무:
1. changes_log를 읽고 expected changes를 정리합니다.
2. state_diff와 스냅샷을 읽고 actual changes를 정리합니다.
3. expected changes와 actual changes를 비교해 unexpected changes를 찾습니다.
4. expected changes 중 실제 반영되지 않은 missing expected changes를 찾습니다.
5. 의도된 변경만 있고 누락도 없으면 is_consistent=true로 판단합니다.

판단 규칙:
- 스냅샷 차이 계산은 이미 Python이 수행했습니다. 당신은 diff를 해석하고 의미를 판단하는 역할만 합니다.
- changes_log에 없는 추가 변경은 unexpected changes에 넣습니다.
- changes_log에서 기대되지만 diff나 스냅샷에서 보이지 않는 변경은 missing expected changes에 넣습니다.
- expected changes, actual changes, unexpected changes, missing expected changes를 각각 명시적으로 작성합니다.
- reasoning은 짧고 구체적으로 작성합니다.
"""

_STEP_VALIDATION_SYSTEM = """\
당신은 planner step과 executor 실행 로그가 같은 작업을 의미하는지 판정하는 검증기입니다.

입력으로 아래 두 항목이 제공됩니다.
- planner_step: step_id, description, action_type, target_file
- executor_log: step_id, tool_name, success, modified_files

판정 목표:
- 같은 step_id로 이미 대응된 planner step 1개와 executor log 1개가 의미상 맞는지 판단합니다.

판단 규칙:
- tool_name을 주 비교 근거로 사용합니다.
- modified_files는 보조 근거로만 사용합니다.
- query step은 modified_files가 비어 있어도 불일치로 단정하지 않습니다.
- create/update/delete step도 modified_files만으로 성공/실패를 단정하지 않습니다.
- tool_name이 planner의 action_type, target_file, description과 명백히 어긋나면 is_match=false입니다.
- structured_skip_* 같은 tool_name은 planner step의 의도와 설명상 자연스러우면 일치로 볼 수 있습니다.
- reasoning은 짧고 구체적으로 작성합니다.
- 출력은 is_match와 reasoning만 제공합니다.
"""


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _build_summary_prompt(state: AgentState) -> list[BaseMessage]:
    validation_results = state.get("validation_results", [])
    success = state.get("success", True)

    user_content = f"""## overall_success
{success}

## validation_results
{_json_dumps(validation_results)}
"""

    return [
        SystemMessage(content=_SUMMARY_SYSTEM),
        HumanMessage(content=user_content),
    ]


def _build_content_validation_prompt(state: AgentState) -> list[BaseMessage]:
    user_content = f"""## expected changes source: changes_log
{_json_dumps(state.get("changes_log", []))}

## actual changes source: state_diff
{_json_dumps(state.get("state_diff", []))}

## current_game_state
{_json_dumps(state.get("current_game_state", {}))}

## modified_game_state
{_json_dumps(state.get("modified_game_state", {}))}
"""

    return [
        SystemMessage(content=_CONTENT_VALIDATION_SYSTEM),
        HumanMessage(content=user_content),
    ]


def _build_step_validation_prompt(state: AgentState) -> list[BaseMessage]:
    user_content = f"""## planner_step
{_json_dumps(state.get("planner_step", {}))}

## executor_log
{_json_dumps(state.get("executor_log", {}))}
"""

    return [
        SystemMessage(content=_STEP_VALIDATION_SYSTEM),
        HumanMessage(content=user_content),
    ]


def build_prompt(state: AgentState) -> list[BaseMessage]:
    mode = str(state.get("_validator_prompt_mode", "summary")).lower()
    if mode == "content_validation":
        return _build_content_validation_prompt(state)
    if mode == "step_validation":
        return _build_step_validation_prompt(state)
    return _build_summary_prompt(state)
