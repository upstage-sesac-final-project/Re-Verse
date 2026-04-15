"""MCP 스모크 테스트 (컨테이너/EC2용).

pytest가 프로덕션 이미지에 없더라도, 아래처럼 실행해서 MCP 연결을 확인할 수 있습니다.

  uv run python -m agent.tests.editor.check_mcp_smoke

필요 환경 변수:
  MCP_ENABLED=true
  MCP_NODE_SERVER_PATH=/app/mcp-server/dist/index.js  (Docker 기본)
  STORAGE_PATH=/app/storage/games                      (또는 기본값 ./storage/games)

선택:
  MCP_TIMEOUT=30
  MCP_PATH_ARG_NAME=targetDir
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from agent.mcp_toolbox import call_mcp_tool, is_mcp_enabled, resolve_game_data_path


async def _main() -> int:
    if not is_mcp_enabled():
        print("MCP_ENABLED가 꺼져 있습니다. (MCP_ENABLED=true 필요)")
        return 2

    game_id = os.environ.get("GAME_ID", "game_001")
    data_path: Path = resolve_game_data_path(game_id)

    # 통합 MCP(integration_MCP) 기준: create_actor(name 필수)
    # tool-registry.json의 canonical 이름 사용 (add_actor는 별칭)
    result = await call_mcp_tool(
        tool_name="create_actor",
        arguments={"name": "ZZZ_MCP_SMOKE_ACTOR"},
        game_data_path=data_path,
    )

    ok = bool(result.get("success"))
    print("MCP call_tool success =", ok)
    if not ok:
        print("error =", result.get("error"))
        return 1

    print(
        "data keys =",
        sorted((result.get("data") or {}).keys())
        if isinstance(result.get("data"), dict)
        else type(result.get("data")),
    )
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
