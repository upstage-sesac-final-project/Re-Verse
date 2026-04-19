"""LLM Service — LangGraph Agent 호출 + Synthesizer 응답 전달."""

import asyncio
import logging
import time
from typing import Any

from langchain_community.callbacks.manager import get_openai_callback
from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.config import agent_config
from app.backend.core.config import settings
from app.backend.repositories.project_repository import project_repository
from app.backend.schemas.llm import ChangeLog, ProcessResponse
from app.backend.services.game_service import game_service
from app.backend.services.s3_game_storage import sync_game_to_s3
from app.backend.services.session_manager import get_game_lock, is_active, touch_session
from app.backend.utils.discord_alerts import send_discord_token_alert

logger = logging.getLogger(__name__)


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

        # ② 세션 활성 검증 (S3 모드)
        if settings.STORAGE_BACKEND == "s3" and not is_active(game_id):
            return ProcessResponse(
                code=400,
                message="편집 세션이 활성화되지 않았습니다. 에디터를 다시 열어주세요.",
                intent="error",
                success=False,
            )

        # ③ Game-Level Lock
        lock = await get_game_lock(game_id)
        async with lock:
            start_time = time.time()
            logger.debug("[LLMService] game lock 획득 | game_id=%s", game_id)

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
            except (TimeoutError, asyncio.CancelledError) as te:
                # asyncio.wait_for 가 timeout 시 내부에서 CancelledError 로 전파될 수도 있음.
                # 둘 다 "사용자에게 timeout 으로 보이는 장애" 로 통일 처리.
                processing_time = time.time() - start_time
                logger.error(
                    "[LLMService] Agent 타임아웃 | game_id=%s, elapsed=%.1fs, cause=%s",
                    game_id,
                    processing_time,
                    type(te).__name__,
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

            # ⑤ 백그라운드 S3 업로드 (성공 시, fire-and-forget 안전장치)
            if settings.STORAGE_BACKEND == "s3" and result["success"]:
                asyncio.create_task(self._background_s3_upload(game_id))

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

    # ── 백그라운드 S3 업로드 ────────────────────────────────

    async def _background_s3_upload(self, game_id: str) -> None:
        """Fire-and-forget S3 업로드 (안전장치). 실패해도 사용자에게 전파하지 않음."""
        try:
            await asyncio.to_thread(sync_game_to_s3, game_id)
            touch_session(game_id)
            logger.info("[LLMService] 백그라운드 S3 업로드 완료 | game_id=%s", game_id)
        except Exception:
            logger.warning(
                "[LLMService] 백그라운드 S3 업로드 실패 | game_id=%s", game_id, exc_info=True
            )

    # ── Agent 호출 ────────────────────────────────────────

    async def _call_graph_agent(
        self, message: str, game_id: str, conversation_history: list[dict] | None = None
    ) -> dict[str, Any]:
        """LangGraph 워크플로우 호출 (Synthesizer 포함)."""
        from agent.editor.workflow import graph

        initial_state: dict[str, Any] = {
            "user_input": message,
            "game_id": game_id,
            "conversation_history": conversation_history or [],
        }
        with get_openai_callback() as cb:
            final_state = await asyncio.wait_for(
                graph.ainvoke(initial_state),  # type: ignore[attr-defined]
                timeout=self.timeout,
            )

        await send_discord_token_alert(
            session_id=game_id,
            prompt_tokens=cb.prompt_tokens,
            completion_tokens=cb.completion_tokens,
            total_cost=cb.total_cost,
            agent_node="Chat Agent (agent.editor.workflow)",
        )

        # executor_v2 는 modified_file_paths (절대 경로 list) 를 내고,
        # legacy 경로는 modified_game_state (dict) 를 내던 이중 상태.
        # 어느 쪽이든 파일명만 뽑아 affected_files 로 반환.
        modified_paths: list[str] = final_state.get("modified_file_paths", []) or []
        modified_state: dict = final_state.get("modified_game_state", {}) or {}
        from pathlib import Path as _Path

        affected_files = sorted(
            set([_Path(p).name for p in modified_paths if p] + list(modified_state.keys()))
        )
        success = final_state.get("success", True)

        return {
            # Synthesizer(6단계)가 생성한 사용자 대상 최종 자연어 응답
            "message": final_state.get("final_response", ""),
            # Router(1단계)가 분류한 사용자 의도
            "intent": final_state.get("intent", ""),
            # 전체 검증 통과 여부
            "success": success,
            # Executor 가 수정한 게임 JSON 파일명 목록
            "affected_files": affected_files,
            # 수정된 파일이 있으면 True → 프론트엔드 게임 리로드 필요
            "reload_required": bool(affected_files),
            # Executor 가 누적한 단계별 변경 이력 리스트
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
