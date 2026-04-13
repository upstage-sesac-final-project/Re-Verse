"""Full Generation REST + WebSocket 엔드포인트.

canonical: docs/The_world/generation_api.md
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §8
"""

import asyncio
import logging
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from agent.generation.progress import publish_progress, subscribe_generation_events
from agent.generation.workflow import run_generation_workflow
from app.backend.core.config import settings
from app.backend.core.security import decode_access_token, get_current_user
from app.backend.db.session import get_db
from app.backend.models.user import User
from app.backend.repositories.project_repository import project_repository
from app.backend.repositories.user_repository import user_repository
from app.backend.schemas.generation import (
    GenerationRequest,
    GenerationStartResponse,
    GenerationStatusResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# 인메모리 상태 저장소 (Phase 2: DB 없이 메모리만 사용)
# {generation_id: GenerationStatusResponse}
_generation_states: dict[str, GenerationStatusResponse] = {}

# 소유권 저장소: {generation_id: user_id}
_generation_owners: dict[str, int] = {}


async def _run_generation_in_background(
    generation_id: str,
    game_id: str,
    prompt: str,
    options: dict,
) -> None:
    """백그라운드 생성 태스크."""
    _generation_states[generation_id] = GenerationStatusResponse(
        generation_id=generation_id,
        status="in_progress",
        phase="spec",
        progress=0,
    )

    try:
        phase_limit = options.get("phase_limit")  # None → 전체 생성
        map_source = options.get("map_source")  # "samples" → 샘플맵 선택기 사용
        final_state = await run_generation_workflow(
            prompt=prompt,
            game_id=game_id,
            generation_id=generation_id,
            phase_limit=phase_limit,
            map_source=map_source,
            options=options,
        )

        is_success = final_state.get("is_success", False)

        if final_state.get("final_project"):
            from agent.generation.writer import write_project_to_disk

            await write_project_to_disk(game_id, final_state["final_project"])
            if settings.STORAGE_BACKEND == "s3":
                from app.backend.services.s3_game_storage import sync_game_to_s3

                sync_game_to_s3(game_id)

        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="completed" if is_success else "completed_with_warnings",
            progress=100,
            completed_phases=final_state.get("completed_phases", []),
            is_success=is_success,
            final_message=final_state.get("final_message"),
            validation_errors=final_state.get("validation_errors", []),
        )

    except Exception as exc:
        logger.exception("generation 실패: gen_id=%s", generation_id)
        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="failed",
            error_message=str(exc),
        )
        await publish_progress(
            generation_id,
            {
                "type": "error",
                "message": f"생성 실패: {exc}",
            },
        )


@router.post("", status_code=202, response_model=GenerationStartResponse)
async def start_generation(
    req: GenerationRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> GenerationStartResponse:
    """게임 생성 시작 → generation_id 즉시 반환."""
    project = await project_repository.find_by_id(req.project_id, db)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="프로젝트를 찾을 수 없습니다.")

    generation_id = f"gen_{uuid4().hex[:8]}"
    _generation_owners[generation_id] = current_user.id
    logger.info(
        "start_generation: user_id=%d project_id=%d game_id=%s gen_id=%s",
        current_user.id,
        req.project_id,
        project.game_id,
        generation_id,
    )

    background_tasks.add_task(
        _run_generation_in_background,
        generation_id=generation_id,
        game_id=project.game_id,
        prompt=req.prompt,
        options=req.options.model_dump(),
    )

    return GenerationStartResponse(
        generation_id=generation_id,
        status="started",
        estimated_seconds=60,
        ws_url=f"/api/v1/generate/ws/{generation_id}",
    )


@router.get("/{generation_id}/status", response_model=GenerationStatusResponse)
async def get_generation_status(
    generation_id: str,
    current_user: User = Depends(get_current_user),
) -> GenerationStatusResponse:
    """진행 상황 폴링."""
    state = _generation_states.get(generation_id)
    if state is None or _generation_owners.get(generation_id) != current_user.id:
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.")
    return state


@router.delete("/{generation_id}", status_code=204)
async def cancel_generation(
    generation_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """생성 취소 (현재: 상태만 cancelled로 변경)."""
    if (
        generation_id not in _generation_states
        or _generation_owners.get(generation_id) != current_user.id
    ):
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.")
    _generation_states[generation_id] = GenerationStatusResponse(
        generation_id=generation_id,
        status="cancelled",
    )
    await publish_progress(generation_id, {"type": "error", "message": "취소됨"})


@router.websocket("/ws/{generation_id}")
async def generation_websocket(
    websocket: WebSocket,
    generation_id: str,
    token: str = Query(..., description="JWT access token"),
    db: AsyncSession = Depends(get_db),
) -> None:
    """생성 진행률 실시간 스트리밍 WebSocket.

    브라우저 WebSocket API는 Authorization 헤더를 지원하지 않으므로
    ?token=<access_token> 쿼리 파라미터로 인증합니다.
    """
    # 토큰 검증
    payload = decode_access_token(token)
    if payload is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id = payload.get("sub")
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user = await user_repository.find_by_id(int(user_id), db)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 소유권 확인
    if _generation_owners.get(generation_id) != user.id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WebSocket 연결: gen_id=%s user_id=%d", generation_id, user.id)

    try:
        async for event in subscribe_generation_events(generation_id):
            await websocket.send_json(event)
            if event.get("type") in ("completed", "completed_with_warnings", "error"):
                break
    except WebSocketDisconnect:
        logger.info("WebSocket 연결 해제: gen_id=%s", generation_id)
    except asyncio.CancelledError:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
