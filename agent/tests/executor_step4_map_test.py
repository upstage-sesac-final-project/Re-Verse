"""파이프라인 4단계(Executor)만 맵 MCP 경로를 검증하는 스크립트.

Router(1) → Definition(2) → Planner(3) 없이 `execution_plan`을 직접 구성해
Executor만 호출합니다.

## 시나리오 (--scenario)

사용자가 채팅으로 할 법한 말에 **대응하는 테스트 플랜**을 고를 수 있습니다.

| --scenario      | 예시 질문 (의도) |
|-----------------|------------------|
| list-maps       | 맵 종류 알려줘, 맵 목록 보여줘, 어떤 맵 있어? |
| add-map         | 새 맵 추가해줘, 맵 하나 만들어줘 (MapInfos + create_map, **변경**) |
| get-map         | 1번 맵 데이터 보여줘, 이 맵 정보 알려줘 |
| list-events     | 1번 맵에 이벤트 뭐 있어? |
| search-events   | 1번 맵 이벤트에서 OO 검색 |
| readonly-full   | (기본) 목록 → 맵 조회 → 이벤트 목록 연속 스모크 |

필수:
  - `STORAGE_PATH` 아래 해당 `game_id`의 `data/` 존재
  - 맵 MCP: `MCP_ENABLED=true` 및 MCP 서버 설정

실행 예:

  MCP_ENABLED=true GAME_ID=game_xxx uv run python -m agent.tests.executor_step4_map_test --scenario list-maps

  uv run python -m agent.tests.executor_step4_map_test --scenario add-map --game-id game_xxx --map-name 시험용던전

  uv run python -m agent.tests.executor_step4_map_test --scenario search-events --map-id 1 --search-term 고블린
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

from agent.graph.nodes.executor import executor
from agent.graph.state import AgentState
from agent.mcp_toolbox import is_mcp_enabled

# 시나리오 → 사용자에게 보여 줄 「채팅 예시」(플랜 설명과 함께 출력)
SCENARIO_USER_PHRASES: dict[str, str] = {
    "readonly-full": "「맵 목록이랑, 지정 맵·이벤트까지 한 번에 확인해줘」",
    "list-maps": "「맵 종류(목록) 알려줘」",
    "add-map": "「새로운 맵 추가해줘」",
    "get-map": "「N번 맵 정보(데이터) 알려줘」",
    "list-events": "「N번 맵 이벤트 목록 알려줘」",
    "search-events": "「N번 맵에서 특정 문자열로 이벤트 검색해줘」",
}


def _map_filename(map_id: int) -> str:
    return f"Map{map_id:03d}.json"


def _step(
    step_id: int,
    description: str,
    action_type: str,
    target_file: str,
    target_info: dict[str, Any],
    depends_on: list[int] | None = None,
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "description": description,
        "action_type": action_type,
        "target_file": target_file,
        "target_info": target_info,
        "depends_on": depends_on or [],
        "condition": "",
    }


def build_plan_readonly_full(map_id: int) -> list[dict[str, Any]]:
    mf = _map_filename(map_id)
    return [
        _step(1, f"{SCENARIO_USER_PHRASES['list-maps']} → list_maps", "query", "MapInfos.json", {}),
        _step(2, f"{SCENARIO_USER_PHRASES['get-map']} → get_map ({mf})", "query", mf, {}),
        _step(
            3,
            f"{SCENARIO_USER_PHRASES['list-events']} → get_map_events ({mf})",
            "list_events",
            mf,
            {},
        ),
    ]


def build_plan_list_maps() -> list[dict[str, Any]]:
    return [
        _step(
            1,
            f"{SCENARIO_USER_PHRASES['list-maps']} → list_maps",
            "query",
            "MapInfos.json",
            {},
        ),
    ]


def build_plan_add_map(
    map_name: str,
    width: int,
    height: int,
    tileset_id: int,
) -> list[dict[str, Any]]:
    return [
        _step(
            1,
            f"{SCENARIO_USER_PHRASES['add-map']} → create_map",
            "create",
            "MapInfos.json",
            {
                "mapName": map_name,
                "width": width,
                "height": height,
                "tilesetId": tileset_id,
            },
        ),
    ]


def build_plan_get_map(map_id: int) -> list[dict[str, Any]]:
    mf = _map_filename(map_id)
    return [
        _step(
            1,
            f"{SCENARIO_USER_PHRASES['get-map']} → get_map ({mf})",
            "query",
            mf,
            {},
        ),
    ]


def build_plan_list_events(map_id: int) -> list[dict[str, Any]]:
    mf = _map_filename(map_id)
    return [
        _step(
            1,
            f"{SCENARIO_USER_PHRASES['list-events']} → get_map_events ({mf})",
            "list_events",
            mf,
            {},
        ),
    ]


def build_plan_search_events(map_id: int, search_term: str) -> list[dict[str, Any]]:
    mf = _map_filename(map_id)
    return [
        _step(
            1,
            f"{SCENARIO_USER_PHRASES['search-events']} → search_map_events ({mf})",
            "search",
            mf,
            {"searchTerm": search_term},
        ),
    ]


def build_plan_for_scenario(
    scenario: str,
    *,
    map_id: int,
    map_name: str | None,
    width: int,
    height: int,
    tileset_id: int,
    search_term: str,
) -> list[dict[str, Any]]:
    if scenario == "readonly-full":
        return build_plan_readonly_full(map_id)
    if scenario == "list-maps":
        return build_plan_list_maps()
    if scenario == "add-map":
        name = map_name or f"RV_TEST_MAP_{uuid.uuid4().hex[:8]}"
        return build_plan_add_map(name, width, height, tileset_id)
    if scenario == "get-map":
        return build_plan_get_map(map_id)
    if scenario == "list-events":
        return build_plan_list_events(map_id)
    if scenario == "search-events":
        return build_plan_search_events(map_id, search_term)
    raise ValueError(f"unknown scenario: {scenario}")


async def _run(
    game_id: str,
    scenario: str,
    map_id: int,
    map_name: str | None,
    width: int,
    height: int,
    tileset_id: int,
    search_term: str,
) -> int:
    if not is_mcp_enabled():
        print(
            "MCP가 꺼져 있습니다. 예: MCP_ENABLED=true\n"
            "  (맵 스텝은 MCP 매핑을 타는 경우가 많습니다.)",
            file=sys.stderr,
        )
        return 2

    from app.backend.core.config import settings

    data_dir = Path(settings.STORAGE_PATH) / game_id / "data"
    if not data_dir.is_dir():
        print(f"데이터 폴더가 없습니다: {data_dir}", file=sys.stderr)
        return 3

    plan = build_plan_for_scenario(
        scenario,
        map_id=map_id,
        map_name=map_name,
        width=width,
        height=height,
        tileset_id=tileset_id,
        search_term=search_term,
    )

    mutating = scenario in ("add-map",)
    if mutating:
        print("⚠️  이 시나리오는 맵 메타/파일을 **변경**할 수 있습니다. (add-map)", file=sys.stderr)

    phrase = SCENARIO_USER_PHRASES.get(scenario, "")
    state: AgentState = {
        "game_id": game_id,
        "retry_count": 0,
        "user_input": f"[executor_step4_map_test] scenario={scenario} {phrase}",
        "execution_plan": plan,
    }

    print("─── Executor step 4 only (map MCP) ───")
    print(f"  시나리오: {scenario}  {phrase}")
    print(f"  game_id={game_id}  map_id={map_id}  data={data_dir}")
    print("  steps:", len(plan))
    for s in plan:
        print(
            f"    - {s.get('step_id')}: {s.get('target_file')} {s.get('action_type')} — {s.get('description')}"
        )

    result = await executor(state)
    logs = result.get("changes_log") or []

    print("\n─── changes_log 요약 ───")
    for entry in logs:
        ok = entry.get("success")
        tool = entry.get("tool_name", "?")
        sid = entry.get("step_id", entry.get("step", "?"))
        err = entry.get("error") or entry.get("stderr") or ""
        line = f"  step {sid}  {tool}  success={ok}"
        if err and not ok:
            line += f"  err={str(err)[:200]}"
        print(line)

    out_path = result.get("modified_file_paths") or []
    if out_path:
        print("\nmodified_file_paths:", out_path)

    failed = sum(1 for e in logs if e.get("success") is False)
    if failed:
        print(json.dumps(logs, ensure_ascii=False, indent=2, default=str))
        return 1
    return 0


def main() -> None:
    scenarios = list(SCENARIO_USER_PHRASES.keys())
    p = argparse.ArgumentParser(
        description="Executor(4단계)만 맵 관련 execution_plan으로 실행 (채팅 시나리오 대응)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="시나리오별 예시 질문은 모듈 상단 docstring 표를 참고하세요.",
    )
    p.add_argument(
        "--scenario",
        "-s",
        choices=scenarios,
        default="readonly-full",
        help=f"테스트 시나리오 (기본: readonly-full). 선택지: {', '.join(scenarios)}",
    )
    p.add_argument(
        "--game-id",
        default=os.environ.get("GAME_ID", "").strip() or None,
        help="스토리지 게임 ID (기본: 환경 변수 GAME_ID)",
    )
    p.add_argument(
        "--map-id",
        type=int,
        default=1,
        help="MapNNN.json 의 N (기본 1). get-map / list-events / search-events 등",
    )
    p.add_argument(
        "--map-name",
        default=None,
        help="add-map 시 맵 이름 (생략 시 RV_TEST_MAP_<랜덤>)",
    )
    p.add_argument("--width", type=int, default=20, help="add-map 시 맵 너비 (기본 20)")
    p.add_argument("--height", type=int, default=15, help="add-map 시 맵 높이 (기본 15)")
    p.add_argument("--tileset-id", type=int, default=1, help="add-map 시 타일셋 ID (기본 1)")
    p.add_argument(
        "--search-term",
        default="",
        help="search-events 시 검색어 (필수에 가깝게 — 빈 문자열이면 의미 없는 검색)",
    )
    args = p.parse_args()

    if not args.game_id:
        print("--game-id 또는 환경 변수 GAME_ID 가 필요합니다.", file=sys.stderr)
        sys.exit(2)

    if args.scenario == "search-events" and not (args.search_term or "").strip():
        print("--search-term 이 비어 있습니다. 예: --search-term 고블린", file=sys.stderr)
        sys.exit(2)

    raise SystemExit(
        asyncio.run(
            _run(
                args.game_id,
                args.scenario,
                args.map_id,
                args.map_name,
                args.width,
                args.height,
                args.tileset_id,
                (args.search_term or "").strip(),
            )
        )
    )


if __name__ == "__main__":
    main()
