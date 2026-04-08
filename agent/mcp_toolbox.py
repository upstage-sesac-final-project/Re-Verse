"""MCP(stdio) 클라이언트 + 게임 저장소 경로 헬퍼.

역할
----
- **경로**: `STORAGE_PATH`는 항상 `app.backend.core.game_paths`와 동일한 기준을 씁니다.
  Executor가 넘기는 `game_data_path`가 그 루트 밖을 가리키면 MCP를 호출하지 않습니다.
- **MCP**: Node 등으로 띄운 RPG Maker MZ MCP 서버와 stdio로 통신해 `call_tool`만 수행합니다.
  (Cursor `mcp.json`과 별개 — **백엔드 프로세스**에서만 사용.)

환경 변수 (`.env` / Docker)
---------------------------
  MCP_ENABLED=true|false     … 기본 false. true일 때만 Executor가 MCP 분기 시도.
  MCP_NODE_SERVER_PATH=…     … 빌드된 `index.js` 절대 경로. 있으면 command는 기본 `node`.
  MCP_COMMAND=node           … (선택) 서버 실행 파일. 비어 있으면 `MCP_NODE_SERVER_PATH`만 쓸 때 `node` 사용.
  MCP_ARGS=["/path/index.js"] … (선택) JSON 배열 또는 단일 문자열. `MCP_COMMAND`와 함께 쓸 때 인자 목록.
  MCP_CWD=…                  … (선택) MCP 프로세스 작업 디렉터리.
  MCP_ENV_JSON={"KEY":"v"}   … (선택) 자식 프로세스에 추가로 넘길 env (기본은 부모 `os.environ` 병합).
  MCP_TIMEOUT=30             … (선택) 한 번의 `call_tool` 대기 초. 기본 30.
  MCP_PATH_ARG_NAME=targetDir … (선택) 게임 `data/` 경로를 넣을 툴 인자 키. k4zuki 서버 README에 맞게 조정.
  MCP_SERVERS_JSON=…          … (선택) 여러 stdio MCP 바이너리를 이름으로 등록. 설정 시 단일 `MCP_NODE_SERVER_PATH`보다 우선.
  MCP_DEFAULT_SERVER=default … (선택) `MCP_SERVERS_JSON` 사용 시, 아래 라우팅으로도 키가 안 정해지면 쓸 서버 키. 기본 `default`.
  MCP_SERVER_BY_TARGET_FILE_JSON=… … (선택) `{"Actors.json":"default",...}` — `target_file` → `MCP_SERVERS_JSON` 키.
  MCP_SERVER_BY_TOOL_JSON=…   … (선택) `{"get_actor":"mcp_maker",...}` — MCP 툴 이름 → 서버 키 (`mcp_server`/파일 매핑보다 우선).

Executor(4단계)에서는 `is_mcp_enabled()`가 참이고 `(target_file, action)`이 `MCP_TOOL_MAP`에 있을 때만
`call_mcp_tool`을 호출합니다. 실패 시 기존 Python 매니저로 폴백할 수 있습니다.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

from app.backend.core.game_paths import (
    ensure_rpgmaker_mz_project_shell,
    get_game_data_path,
    get_storage_root,
)

logger = logging.getLogger(__name__)


def is_mcp_enabled() -> bool:
    """MCP 분기를 탈지 여부. 꺼 두면 기존 ActorManager 등만 사용."""
    return os.environ.get("MCP_ENABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def resolve_game_data_path(game_id: str) -> Path:
    """`game_id`에 대한 RPG Maker `data/` 디렉터리 절대 경로."""
    return get_game_data_path(game_id).resolve()


def resolve_storage_root() -> Path:
    """`STORAGE_PATH` 기준 루트 (`…/storage/games`). Executor 샌드박스 검증에 사용."""
    return get_storage_root()


def get_mcp_stdio_env() -> dict[str, str]:
    """`MCP_ENV_JSON`으로 자식 프로세스에만 추가할 키=값."""
    raw = os.environ.get("MCP_ENV_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}
        return {str(k): str(v) for k, v in data.items()}
    except json.JSONDecodeError:
        logger.warning("MCP_ENV_JSON 파싱 실패 — 무시합니다.")
        return {}


def get_mcp_server_args() -> list[str]:
    """`MCP_ARGS`: JSON 배열이면 파싱, 아니면 한 덩어리 문자열을 단일 인자로."""
    raw = os.environ.get("MCP_ARGS", "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
        except json.JSONDecodeError:
            pass
    return [raw]


def parse_mcp_servers_json() -> dict[str, dict[str, Any]] | None:
    """`MCP_SERVERS_JSON`: 서버 id → { node_path?, command?, args?, cwd? }.

    유효한 객체가 없으면 None (레거시 단일 경로 설정 사용).
    """
    raw = os.environ.get("MCP_SERVERS_JSON", "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("MCP_SERVERS_JSON 파싱 실패 — 레거시 MCP_NODE_SERVER_PATH만 사용합니다.")
        return None
    if not isinstance(data, dict) or not data:
        return None
    out: dict[str, dict[str, Any]] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, dict):
            out[k] = v
    return out or None


def _stdio_params_from_server_entry(
    entry: dict[str, Any],
    extra_env: dict[str, str] | None,
) -> Any | None:
    """서버 항목 dict로 `StdioServerParameters` 생성."""
    from mcp.client.stdio import StdioServerParameters

    node_path = str(entry.get("node_path") or "").strip()
    cmd = str(entry.get("command") or "").strip()
    raw_args = entry.get("args")
    if isinstance(raw_args, list):
        args = [str(x) for x in raw_args]
    else:
        args = []

    if not cmd and node_path:
        cmd = "node"
        args = [node_path]
    elif cmd and not args and node_path:
        args = [node_path]
    elif not cmd:
        return None

    if not args:
        return None

    merged_env = {**os.environ, **get_mcp_stdio_env(), **(extra_env or {})}
    cwd = str(entry.get("cwd") or "").strip() or os.environ.get("MCP_CWD", "").strip() or None
    return StdioServerParameters(command=cmd, args=args, env=merged_env, cwd=cwd)


def _build_stdio_server_parameters_legacy(extra_env: dict[str, str] | None) -> Any | None:
    """단일 `MCP_NODE_SERVER_PATH` / `MCP_COMMAND` + `MCP_ARGS` (기존 동작)."""
    from mcp.client.stdio import StdioServerParameters

    node_path = os.environ.get("MCP_NODE_SERVER_PATH", "").strip()
    cmd = os.environ.get("MCP_COMMAND", "").strip()
    args = get_mcp_server_args()

    if not cmd and node_path:
        cmd = "node"
        args = [node_path]
    elif cmd and not args and node_path:
        args = [node_path]
    elif not cmd:
        return None

    merged_env = {**os.environ, **get_mcp_stdio_env(), **(extra_env or {})}
    cwd = os.environ.get("MCP_CWD", "").strip() or None
    return StdioServerParameters(command=cmd, args=args, env=merged_env, cwd=cwd)


def build_stdio_server_parameters(
    extra_env: dict[str, str] | None = None,
    *,
    mcp_server: str | None = None,
) -> Any | None:
    """`mcp.client.stdio.StdioServerParameters` 인스턴스 또는 설정 불가 시 None.

    우선순위:
    1. `MCP_SERVERS_JSON`이 있으면 → 이름 `mcp_server`(없으면 `MCP_DEFAULT_SERVER`, 기본 키 `default`)로 항목 선택
    2. 아니면 레거시: `MCP_NODE_SERVER_PATH`만 있으면 → `node` + `[경로]`
    3. 레거시: `MCP_COMMAND` + `MCP_ARGS` (또는 `MCP_NODE_SERVER_PATH`를 보조 인자로)
    """
    servers = parse_mcp_servers_json()
    if servers:
        key = (mcp_server or "").strip() or os.environ.get("MCP_DEFAULT_SERVER", "default").strip()
        if not key:
            key = "default"
        entry = servers.get(key)
        if not isinstance(entry, dict):
            logger.warning("MCP_SERVERS_JSON에 서버 키가 없습니다: %s", key)
            return None
        return _stdio_params_from_server_entry(entry, extra_env)

    return _build_stdio_server_parameters_legacy(extra_env)


def _load_mcp_string_mapping_json(env_key: str) -> dict[str, str]:
    """환경변수 JSON 객체를 str→str 맵으로 로드. 실패·비어 있으면 {}."""
    raw = os.environ.get(env_key, "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("%s 파싱 실패 — 무시합니다.", env_key)
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for k, v in data.items():
        if isinstance(k, str) and isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def resolve_mcp_server_key(
    target_file: str,
    tool_name: str | None,
    explicit_from_map: str | None = None,
) -> str | None:
    """어떤 `MCP_SERVERS_JSON` 키로 stdio를 띄울지 결정.

    우선순위:
    1. `MCP_TOOL_MAP`의 `mcp_server` (explicit_from_map)
    2. `MCP_SERVER_BY_TOOL_JSON`[tool_name]
    3. `MCP_SERVER_BY_TARGET_FILE_JSON`[target_file]
    4. None → `build_stdio_server_parameters`에서 `MCP_DEFAULT_SERVER` 사용
    """
    if explicit_from_map and str(explicit_from_map).strip():
        return str(explicit_from_map).strip()

    tname = (tool_name or "").strip()
    if tname:
        by_tool = _load_mcp_string_mapping_json("MCP_SERVER_BY_TOOL_JSON")
        if tname in by_tool:
            return by_tool[tname]

    tf = (target_file or "").strip()
    if tf:
        by_file = _load_mcp_string_mapping_json("MCP_SERVER_BY_TARGET_FILE_JSON")
        if tf in by_file:
            return by_file[tf]

    return None


def _is_path_under_storage_root(candidate: Path) -> bool:
    """Path traversal 방지: `candidate`가 `STORAGE_PATH` 루트 아래인지."""
    root = get_storage_root().resolve()
    try:
        resolved = candidate.resolve()
    except OSError:
        return False
    try:
        return resolved.is_relative_to(root)
    except (ValueError, AttributeError):
        return False


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    game_data_path: Path,
    *,
    path_arg_name: str | None = None,
    mcp_server: str | None = None,
) -> dict[str, Any]:
    """MCP 서버에 `call_tool` 한 번 보내고, Executor가 쓰기 쉬운 dict로 정규화한다.

    반환 키 (Executor / changes_log와 맞춤):
      - success: bool
      - data: 파싱된 본문(dict) 또는 원문
      - modified_files: list[str] (서버가 주면)
      - error: str | None
    """
    from mcp.client.session import ClientSession
    from mcp.client.stdio import stdio_client

    if not _is_path_under_storage_root(game_data_path):
        return {
            "success": False,
            "error": f"허용되지 않은 경로입니다: {game_data_path}",
            "modified_files": [],
            "data": {},
        }

    # MCP 서버는 RPGMAKER_PROJECT_PATH 환경변수로 게임 루트를 읽는다.
    # game_data_path는 data/ 폴더이므로 .parent가 게임 루트.
    game_root = game_data_path.resolve().parent
    ensure_rpgmaker_mz_project_shell(game_root)
    params = build_stdio_server_parameters(
        extra_env={"RPGMAKER_PROJECT_PATH": str(game_root)},
        mcp_server=mcp_server,
    )
    if params is None:
        return {
            "success": False,
            "error": "MCP 설정 없음(MCP_SERVERS_JSON 항목 또는 MCP_NODE_SERVER_PATH / MCP_COMMAND+MCP_ARGS)",
            "modified_files": [],
            "data": {},
        }

    safe_args = dict(arguments)

    # per-call 타임아웃: 응답 지연 시 전체 워크플로우가 장시간 블로킹되는 것을 방지한다.
    timeout = float(os.environ.get("MCP_TIMEOUT", "30"))

    async def _run() -> Any:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await session.call_tool(tool_name, safe_args)

    try:
        result = await asyncio.wait_for(_run(), timeout=timeout)
    except TimeoutError:
        return {
            "success": False,
            "error": f"MCP 타임아웃 ({timeout}초)",
            "modified_files": [],
            "data": {},
        }
    except Exception as e:
        logger.exception("MCP call_tool 실패 tool=%s", tool_name)
        return {
            "success": False,
            "error": str(e),
            "modified_files": [],
            "data": {},
        }

    if getattr(result, "isError", False):
        raw_err = "".join(c.text for c in getattr(result, "content", []) if hasattr(c, "text"))
        return {
            "success": False,
            "error": raw_err or "MCP isError",
            "modified_files": [],
            "data": {},
        }

    raw_text = "".join(c.text for c in result.content if hasattr(c, "text"))

    # MCP 서버가 에러를 plain text "Error: ..." 형태로 반환하는 경우 (isError 없이)
    if raw_text.strip().startswith("Error:"):
        return {
            "success": False,
            "error": raw_text.strip(),
            "modified_files": [],
            "data": {},
        }

    parsed: dict[str, Any] = {}
    try:
        parsed = json.loads(raw_text) if raw_text.strip() else {}
    except json.JSONDecodeError:
        # 일부 MCP 서버는 순수 텍스트를 반환하므로 원문을 보존한다.
        parsed = {"raw_output": raw_text}

    # MCP 서버가 success 필드를 생략하는 경우도 있어 기본값은 True로 처리한다.
    ok = parsed.get("success", True) if isinstance(parsed, dict) else True
    modified = []
    if isinstance(parsed, dict):
        modified = parsed.get("modified_files") or []

    return {
        "success": bool(ok),
        "data": parsed,
        "modified_files": modified,
        "error": parsed.get("error") if isinstance(parsed, dict) and not ok else None,
    }


def get_mcp_stdio_spec() -> dict[str, Any] | None:
    """디버그용: 현재 환경에서 어떤 stdio 명령이 구성되는지 요약."""
    p = build_stdio_server_parameters()
    if p is None:
        return None
    return {
        "command": getattr(p, "command", None),
        "args": getattr(p, "args", None),
        "cwd": getattr(p, "cwd", None),
    }
