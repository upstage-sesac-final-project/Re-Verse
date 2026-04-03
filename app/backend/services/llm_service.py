"""LLM Service — LangGraph Agent 호출 + Synthesizer 응답 전달."""

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.config import agent_config
from app.backend.core.config import settings
from app.backend.repositories.project_repository import project_repository
from app.backend.schemas.llm import ChangeLog, ProcessResponse
from app.backend.services.game_service import game_service
from app.backend.services.s3_game_storage import sync_game_from_s3, sync_game_to_s3

logger = logging.getLogger(__name__)

# ── Game-Level Lock (동시성 제어) ────────────────────────
_game_locks: dict[str, asyncio.Lock] = {}


async def _get_game_lock(game_id: str) -> asyncio.Lock:
    if game_id not in _game_locks:
        _game_locks[game_id] = asyncio.Lock()
    return _game_locks[game_id]


def remove_game_lock(game_id: str) -> None:
    """프로젝트 삭제 시 해당 lock 정리."""
    _game_locks.pop(game_id, None)


class LLMService:
    """LLM Agent 호출 서비스"""

    def __init__(self) -> None:
        self.timeout = agent_config.AGENT_TIMEOUT
        self.max_retries = agent_config.MAX_RETRIES

    async def process_chat(
        self,
        project_id: int,
        message: str,
        user_id: int,
        db: AsyncSession,
    ) -> ProcessResponse:
        """프로젝트 소유권 확인 -> Agent 호출 -> DB 저장 -> 응답 반환."""

        # ① Project 조회 + 권한 확인
        project = await game_service.get_project(project_id, user_id, db)
        game_id = project.game_id
        logger.info(
            "[LLMService] 처리 시작 | project_id=%d, game_id=%s, user_id=%d",
            project_id,
            game_id,
            user_id,
        )

        # ② Game-Level Lock
        lock = await _get_game_lock(game_id)
        async with lock:
            start_time = time.time()
            logger.debug("[LLMService] game lock 획득 | game_id=%s", game_id)

            # ③ S3 동기화 (프로덕션)
            if settings.STORAGE_BACKEND == "s3":
                logger.info("[LLMService] S3 → 로컬 동기화 시작 | game_id=%s", game_id)
                await asyncio.to_thread(sync_game_from_s3, game_id)

            # ④ Agent 호출
            try:
                logger.info("[LLMService] Agent 호출 시작 | game_id=%s", game_id)
                from agent.memory.conversation_manager import build_conversation_history

                conversation_history = await build_conversation_history(project_id, db)
                result = await self._call_graph_agent(message, game_id, conversation_history)
                logger.info(
                    "[LLMService] Agent 호출 완료 | success=%s, intent=%s, affected_files=%s",
                    result["success"],
                    result["intent"],
                    result.get("affected_files", []),
                )
            except TimeoutError:
                processing_time = time.time() - start_time
                logger.error(
                    "[LLMService] Agent 타임아웃 | game_id=%s, elapsed=%.1fs",
                    game_id,
                    processing_time,
                )
                await self._save_log(
                    db,
                    project_id,
                    message,
                    None,
                    "timeout",
                    False,
                    processing_time,
                    "요청 처리 시간 초과",
                )
                return ProcessResponse(
                    code=504,
                    message="요청 처리 시간이 초과되었습니다.",
                    intent="timeout",
                    success=False,
                )
            except Exception as e:
                processing_time = time.time() - start_time
                logger.error(
                    "[LLMService] Agent 호출 실패 | game_id=%s, error=%s",
                    game_id,
                    e,
                    exc_info=True,
                )
                await self._save_log(
                    db,
                    project_id,
                    message,
                    None,
                    "error",
                    False,
                    processing_time,
                    str(e),
                )
                return ProcessResponse(
                    code=500,
                    message=f"처리 중 오류가 발생했습니다: {e!s}",
                    intent="error",
                    success=False,
                )

            # ⑤ S3 업로드 (성공 시) + 로컬 정리
            if settings.STORAGE_BACKEND == "s3":
                if result["success"]:
                    logger.info("[LLMService] 로컬 → S3 업로드 시작 | game_id=%s", game_id)
                    await asyncio.to_thread(sync_game_to_s3, game_id)
                local_game_dir = Path(settings.STORAGE_PATH).resolve() / game_id
                if local_game_dir.is_dir():
                    await asyncio.to_thread(shutil.rmtree, local_game_dir)
                    logger.info("[LLMService] 로컬 게임 폴더 정리 완료 | %s", local_game_dir)

            processing_time = time.time() - start_time
            logger.info(
                "[LLMService] 처리 완료 | project_id=%d, processing_time=%.2fs",
                project_id,
                processing_time,
            )

            # ⑥ ConversationLog DB 저장
            await self._save_log(
                db=db,
                project_id=project_id,
                user_input=message,
                agent_response=result.get("message", ""),
                intent=result.get("intent"),
                success=result["success"],
                processing_time=processing_time,
                error_message=result.get("error"),
            )

            # ⑦ ProcessResponse 반환
            return ProcessResponse(
                code=201 if result.get("success", False) else 400,
                message=result.get("message", ""),
                intent=result.get("intent"),
                success=result.get("success", False),
                affected_files=result.get("affected_files", []),
                reload_required=result.get("reload_required", False),
                changes_log=[
                    ChangeLog(**log) if isinstance(log, dict) else log
                    for log in result.get("changes_log", [])
                ],
            )

    # ── Agent 호출 ────────────────────────────────────────

    async def _call_graph_agent(
        self, message: str, game_id: str, conversation_history: list[dict] | None = None
    ) -> dict[str, Any]:
        """LangGraph 워크플로우 호출 (Synthesizer 포함)."""
        from agent.graph.workflow import graph

        initial_state: dict[str, Any] = {
            "user_input": message,
            "game_id": game_id,
            "conversation_history": conversation_history or [],
        }
        final_state = await asyncio.wait_for(
            graph.ainvoke(initial_state),  # type: ignore[attr-defined]
            timeout=self.timeout,
        )

        modified = final_state.get("modified_game_state", {})
        success = final_state.get("success", True)

        return {
            # Synthesizer(6단계)가 생성한 사용자 대상 최종 자연어 응답
            "message": final_state.get("final_response", ""),
            # Router(1단계)가 분류한 사용자 의도 (예: "게임_요소_생성", "게임_요소_수정" 등)
            "intent": final_state.get("intent", ""),
            # Validator(5단계) 전체 검증 통과 여부
            "success": success,
            # Executor(4단계)가 수정한 게임 JSON 파일명 목록 (예: ["Skills.json"])
            "affected_files": list(modified.keys()) if modified else [],
            # 수정된 파일이 있으면 True → 프론트엔드 게임 리로드 필요
            "reload_required": bool(modified),
            # Executor(4단계)가 누적한 단계별 변경 이력 리스트
            "changes_log": final_state.get("changes_log", []),
        }

    # ── 대화 이력 저장 ────────────────────────────────────

    async def _save_log(
        self,
        db: AsyncSession,
        project_id: int,
        user_input: str,
        agent_response: str | None,
        intent: str | None,
        success: bool,
        processing_time: float,
        error_message: str | None = None,
    ) -> None:
        await project_repository.save_conversation_log(
            db=db,
            project_id=project_id,
            user_input=user_input,
            agent_response=agent_response,
            intent=intent,
            success=success,
            processing_time=processing_time,
            error_message=error_message,
        )


# 싱글톤 인스턴스
llm_service = LLMService()
