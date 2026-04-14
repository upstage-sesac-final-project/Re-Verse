"""Full Generation REST + WebSocket 엔드포인트.

canonical: docs/The_world/generation_api.md
canonical: docs/The_world/IMPLEMENTATION_GUIDE.md §8
"""

import asyncio
import gc
import logging
import shutil
import time
from collections import deque
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

from agent.generation.progress import (
    publish_progress,
    set_progress_callback,
    subscribe_generation_events,
)
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

# 프로젝트 매핑: {project_id: generation_id} (활성 생성만)
_project_generations: dict[int, str] = {}

# 완료 시각 기록: {generation_id: timestamp}
_completion_times: dict[str, float] = {}

# 상태 dict 동시 접근 보호
_state_lock = asyncio.Lock()

# 동시 생성 제한 (t3.micro: 1개만 동시 실행)
_MAX_CONCURRENT_GENERATIONS = 1
_generation_semaphore = asyncio.Semaphore(_MAX_CONCURRENT_GENERATIONS)
_WAIT_PER_GENERATION = 300  # 1개당 예상 대기 5분

# 대기열: [(generation_id, event)] — event.set() 호출 시 실행 시작
_generation_queue: deque[str] = deque()

# 완료 후 10분 뒤 자동 정리
_CLEANUP_TTL = 600


def _cleanup_stale_states() -> None:
    """완료된 generation 상태를 TTL 후 정리. dict 스냅샷으로 순회."""
    now = time.time()
    stale = [gid for gid, t in list(_completion_times.items()) if now - t > _CLEANUP_TTL]
    for gid in stale:
        _generation_states.pop(gid, None)
        _generation_owners.pop(gid, None)
        _completion_times.pop(gid, None)
        to_remove = [pid for pid, g in list(_project_generations.items()) if g == gid]
        for pid in to_remove:
            _project_generations.pop(pid, None)


def _on_progress(generation_id: str, event: dict) -> None:
    """WS 이벤트 발행 시 _generation_states도 실시간 업데이트."""
    state = _generation_states.get(generation_id)
    if not state:
        return
    progress = event.get("progress")
    phase = event.get("phase")
    message = event.get("message") or event.get("summary")
    if progress is not None and progress > (state.progress or 0):
        state.progress = progress
    if phase:
        state.phase = phase
    if message:
        state.message = message
    completed = event.get("type") == "phase_complete"
    if completed and phase and phase not in (state.completed_phases or []):
        if state.completed_phases is None:
            state.completed_phases = []
        state.completed_phases.append(phase)


set_progress_callback(_on_progress)


async def _run_generation_in_background(
    generation_id: str,
    game_id: str,
    prompt: str,
    options: dict,
) -> None:
    """백그라운드 생성 태스크. 세마포어로 동시 1개만 실행."""
    # 세마포어 여유가 없으면 대기열
    is_busy = _generation_semaphore._value == 0
    _generation_queue.append(generation_id)
    queue_pos = len(_generation_queue)  # 대기열 내 순서 (1부터)

    if is_busy:
        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="queued",
            queue_position=queue_pos,
            queue_wait_seconds=queue_pos * _WAIT_PER_GENERATION,
        )
        await publish_progress(
            generation_id,
            {
                "type": "queued",
                "queue_position": queue_pos,
                "message": f"대기열 {queue_pos}번째 — 약 {queue_pos * 5}분 후 시작",
            },
        )
    else:
        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="in_progress",
            phase="spec",
            progress=0,
        )

    # 세마포어 획득 대기 (앞 생성이 끝날 때까지)
    async with _generation_semaphore:
        # 대기열에서 제거
        if generation_id in _generation_queue:
            _generation_queue.remove(generation_id)
        # 대기열 순서 업데이트 + WS로 알림
        for i, gid in enumerate(_generation_queue):
            state = _generation_states.get(gid)
            if state and state.status == "queued":
                new_pos = i + 1
                state.queue_position = new_pos
                state.queue_wait_seconds = new_pos * _WAIT_PER_GENERATION
                await publish_progress(
                    gid,
                    {
                        "type": "queued",
                        "queue_position": new_pos,
                        "message": f"대기열 {new_pos}번째 — 약 {new_pos * 5}분 후 시작",
                    },
                )

        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="in_progress",
            phase="spec",
            progress=0,
        )
        await publish_progress(
            generation_id,
            {
                "type": "progress",
                "message": "생성을 시작합니다...",
                "progress": 0,
            },
        )

        await _run_generation_core(generation_id, game_id, prompt, options)

    # 생성 완료 후 메모리 해제
    gc.collect()


async def _run_generation_core(
    generation_id: str,
    game_id: str,
    prompt: str,
    options: dict,
) -> None:
    """실제 생성 로직."""

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

            await asyncio.to_thread(write_project_to_disk, game_id, final_state["final_project"])
            if settings.STORAGE_BACKEND == "s3":
                from app.backend.core.game_paths import get_game_root
                from app.backend.services.s3_game_storage import sync_game_to_s3

                await asyncio.to_thread(sync_game_to_s3, game_id)
                local_dir = get_game_root(game_id)
                if local_dir.is_dir():
                    await asyncio.to_thread(shutil.rmtree, local_dir)

        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="completed" if is_success else "completed_with_warnings",
            progress=100,
            completed_phases=final_state.get("completed_phases", []),
            is_success=is_success,
            final_message=final_state.get("final_message"),
            validation_errors=final_state.get("validation_errors", []),
        )
        _completion_times[generation_id] = time.time()

    except Exception as exc:
        logger.exception("generation 실패: gen_id=%s", generation_id)
        _generation_states[generation_id] = GenerationStatusResponse(
            generation_id=generation_id,
            status="failed",
            error_message=str(exc),
        )
        _completion_times[generation_id] = time.time()
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
    _project_generations[req.project_id] = generation_id
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

    # 현재 대기열 길이 (이 요청 포함)
    active_count = _MAX_CONCURRENT_GENERATIONS - _generation_semaphore._value
    queue_len = len(_generation_queue) + active_count
    queue_pos = max(0, queue_len - 1)

    return GenerationStartResponse(
        generation_id=generation_id,
        status="started",
        estimated_seconds=_WAIT_PER_GENERATION,
        ws_url=f"/api/v1/generate/ws/{generation_id}",
        queue_position=queue_pos,
        queue_wait_seconds=queue_pos * _WAIT_PER_GENERATION,
    )


@router.get("/{generation_id}/status", response_model=GenerationStatusResponse)
async def get_generation_status(
    generation_id: str,
    current_user: User = Depends(get_current_user),
) -> GenerationStatusResponse:
    """진행 상황 폴링."""
    _cleanup_stale_states()
    state = _generation_states.get(generation_id)
    if state is None or _generation_owners.get(generation_id) != current_user.id:
        raise HTTPException(status_code=404, detail="생성 작업을 찾을 수 없습니다.")
    # 대기열 위치 실시간 재계산
    if state.status == "queued":
        try:
            pos = list(_generation_queue).index(generation_id) + 1
            state.queue_position = pos
            state.queue_wait_seconds = pos * _WAIT_PER_GENERATION
        except ValueError:
            pass
    return state


@router.get("/by-project/{project_id}/status", response_model=GenerationStatusResponse)
async def get_generation_status_by_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
) -> GenerationStatusResponse:
    """프로젝트 ID로 활성 생성 상태 조회."""
    generation_id = _project_generations.get(project_id)
    if not generation_id:
        raise HTTPException(status_code=404, detail="활성 생성 작업이 없습니다.")
    state = _generation_states.get(generation_id)
    if state is None or _generation_owners.get(generation_id) != current_user.id:
        raise HTTPException(status_code=404, detail="활성 생성 작업이 없습니다.")
    # 대기열 위치 실시간 재계산
    if state.status == "queued":
        try:
            pos = list(_generation_queue).index(generation_id) + 1
            state.queue_position = pos
            state.queue_wait_seconds = pos * _WAIT_PER_GENERATION
        except ValueError:
            pass
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
) -> None:
    """생성 진행률 실시간 스트리밍 WebSocket.

    브라우저 WebSocket API는 Authorization 헤더를 지원하지 않으므로
    ?token=<access_token> 쿼리 파라미터로 인증합니다.
    DB 세션은 인증 시에만 사용하고 즉시 반환하여 커넥션 풀 고갈을 방지한다.
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

    # DB 세션을 짧게 열고 유저 조회 후 즉시 반환
    from app.backend.db.session import get_db

    verified_user_id = None
    async for db in get_db():
        user = await user_repository.find_by_id(int(user_id), db)
        if user:
            verified_user_id = user.id

    if verified_user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 소유권 확인
    if _generation_owners.get(generation_id) != verified_user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WebSocket 연결: gen_id=%s user_id=%d", generation_id, verified_user_id)

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
        # 큐 명시적 정리 (subscribe_generation_events의 finally와 이중 보장)
        from agent.generation.progress import _generation_queues, _pending_events

        _generation_queues.pop(generation_id, None)
        _pending_events.pop(generation_id, None)
        try:
            await websocket.close()
        except Exception:
            pass
