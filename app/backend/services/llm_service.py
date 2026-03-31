"""LLM Service — Agent 호출 + Synthesizer 응답 전달.

keyword 모드: 기존 키워드 기반 dispatcher 직접 호출 (MVP)
graph 모드:   LangGraph 워크플로우 (Stage 1~6, Synthesizer 포함)
"""

import asyncio
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agent.core.config import agent_config
from app.backend.core.config import settings
from app.backend.models.game import ConversationLog
from app.backend.schemas.llm import ChangeLog, ProcessResponse
from app.backend.services.game_service import game_service
from app.backend.services.json_modify_tools.dispatcher import (
    run_enemies,
    run_items,
    run_levels,
    run_map_villager,
    run_skills,
)
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

        # ② Game-Level Lock
        lock = await _get_game_lock(game_id)
        async with lock:
            start_time = time.time()

            # ③ S3 동기화 (프로덕션)
            if settings.STORAGE_BACKEND == "s3":
                await asyncio.to_thread(sync_game_from_s3, game_id)

            # ④ Agent 호출 (모드 분기)
            try:
                if settings.AGENT_MODE == "graph":
                    result = await self._call_graph_agent(message, game_id)
                else:
                    result = await self._call_keyword_agent(message, game_id)
            except TimeoutError:
                processing_time = time.time() - start_time
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
                    modifications=[],
                    affected_files=[],
                    reload_required=False,
                    success=False,
                )
            except Exception as e:
                processing_time = time.time() - start_time
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
                    modifications=[],
                    affected_files=[],
                    reload_required=False,
                    success=False,
                )

            # ⑤ S3 업로드 (성공 시) + 로컬 정리
            if settings.STORAGE_BACKEND == "s3":
                if result["success"]:
                    await asyncio.to_thread(sync_game_to_s3, game_id)
                local_game_dir = Path(settings.STORAGE_PATH).resolve() / game_id
                if local_game_dir.is_dir():
                    await asyncio.to_thread(shutil.rmtree, local_game_dir)
                    logger.info("로컬 게임 폴더 정리 완료: %s", local_game_dir)

            processing_time = time.time() - start_time

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
                code=201 if result["success"] else 400,
                message=result.get("message", ""),
                result=result.get("result", {}),
                intent=result.get("intent"),
                modifications=result.get("modifications", []),
                affected_files=result.get("affected_files", []),
                changes_log=[
                    ChangeLog(**log) if isinstance(log, dict) else log
                    for log in result.get("changes_log", [])
                ],
                reload_required=result.get("reload_required", False),
                success=result["success"],
            )

    # ── Agent 호출 ────────────────────────────────────────

    async def _call_graph_agent(self, message: str, game_id: str) -> dict[str, Any]:
        """LangGraph 워크플로우 호출 (Synthesizer 포함)."""
        from agent.graph.workflow import graph

        final_state = await asyncio.wait_for(
            graph.ainvoke({"user_input": message, "game_id": game_id}),  # type: ignore[attr-defined]
            timeout=self.timeout,
        )

        validation = final_state.get("validation_result", {})
        modified = final_state.get("modified_game_state", {})

        return {
            "message": final_state.get("final_response", ""),
            "intent": final_state.get("intent", ""),
            "success": validation.get("passed", True),
            "result": {
                "intent": final_state.get("intent", ""),
                "processed": validation.get("passed", True),
            },
            "modifications": list(modified.keys()) if modified else [],
            "affected_files": list(modified.keys()) if modified else [],
            "reload_required": bool(modified),
            "changes_log": final_state.get("changes_log", []),
        }

    async def _call_keyword_agent(self, message: str, game_id: str) -> dict[str, Any]:
        """기존 키워드 기반 MVP 호출."""
        user_input = message.lower()

        tool_name = "none"
        tool_result = None
        intent = "unknown"
        resp_message = "요청을 이해하지 못했습니다. 더 구체적으로 말씀해주세요."

        if any(kw in user_input for kw in ["레벨", "level", "초기레벨", "초기 레벨"]):
            intent, tool_name = "modify_level", "edit_levels"
            resp_message = "레벨을 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_levels, message)

        elif any(
            kw in user_input
            for kw in [
                "스킬",
                "skill",
                "기술",
                "최후의일격",
                "전체공격",
                "회복마법",
                "버프",
                "필살기",
                "강화",
                "공격력강화",
            ]
        ):
            intent, tool_name = "modify_skill", "edit_skills"
            resp_message = "스킬을 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_skills, message)

        elif any(
            kw in user_input for kw in ["적", "몬스터", "몹", "보스", "boss", "적군", "에너미"]
        ):
            intent, tool_name = "modify_enemy", "edit_enemies"
            resp_message = "몬스터를 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_enemies, message)

        elif any(kw in user_input for kw in ["아이템", "템", "item", "장비", "소비템", "소모품"]):
            intent, tool_name = "modify_item", "edit_items"
            resp_message = "아이템을 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_items, message)

        elif any(
            kw in user_input
            for kw in ["맵", "지형", "타일", "지도", "건물", "배경", "환경", "마을"]
        ):
            intent, tool_name = "modify_map", "edit_map_villager"
            resp_message = "맵을 수정하는 중입니다..."
            tool_result = await asyncio.to_thread(run_map_villager, message)

        edit_success = tool_result.get("success", False) if tool_result else False

        if tool_result and not edit_success:
            resp_message = tool_result.get("stderr", resp_message)

        return {
            "message": resp_message,
            "intent": intent,
            "success": edit_success if intent != "unknown" else False,
            "result": {
                "intent": intent,
                "processed": edit_success,
                "user_input": message,
                "modifications": [tool_name] if edit_success else [],
            },
            "modifications": [tool_name] if edit_success else [],
            "affected_files": [],
            "reload_required": edit_success,
            "changes_log": [],
            "error": (tool_result.get("stderr") if tool_result and not edit_success else None),
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
        log = ConversationLog(
            project_id=project_id,
            user_input=user_input,
            agent_response=agent_response,
            intent=intent,
            success=success,
            processing_time=processing_time,
            error_message=error_message,
        )
        db.add(log)
        await db.commit()


# 싱글톤 인스턴스
llm_service = LLMService()
