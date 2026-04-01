"""LLM API 엔드포인트 테스트."""

from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.models.game import ConversationLog, Project


class TestProcessUserInput:
    """POST /api/v1/llm/process"""

    async def test_process_success(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        mock_result = {
            "message": "레벨을 25로 설정했습니다.",
            "intent": "modify_level",
            "success": True,
            "result": {"intent": "modify_level", "processed": True},
            "modifications": ["edit_levels"],
            "affected_files": ["Actors.json"],
            "reload_required": True,
            "changes_log": [],
        }

        with patch(
            "app.backend.services.llm_service.LLMService._call_graph_agent",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            resp = await client.post(
                "/api/v1/llm/process",
                json={"project_id": test_project.id, "message": "레벨을 25로 설정해줘"},
                headers=auth_headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["code"] == 201
        assert data["intent"] == "modify_level"
        assert data["reload_required"] is True

    async def test_process_no_auth(self, client: AsyncClient, test_project: Project):
        resp = await client.post(
            "/api/v1/llm/process",
            json={"project_id": test_project.id, "message": "test"},
        )
        assert resp.status_code == 401

    async def test_process_forbidden_project(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        """다른 사용자의 프로젝트에 LLM 요청 시 403."""
        resp = await client.post(
            "/api/v1/llm/process",
            json={"project_id": test_project.id, "message": "test"},
            headers=other_auth_headers,
        )
        assert resp.status_code == 403

    async def test_process_nonexistent_project(self, client: AsyncClient, auth_headers: dict):
        resp = await client.post(
            "/api/v1/llm/process",
            json={"project_id": 9999, "message": "test"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_process_empty_message(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.post(
            "/api/v1/llm/process",
            json={"project_id": test_project.id, "message": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_process_saves_conversation_log(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        """LLM 처리 후 ConversationLog가 DB에 저장되는지 확인."""
        mock_result = {
            "message": "완료",
            "intent": "modify_level",
            "success": True,
            "result": {},
            "modifications": [],
            "affected_files": [],
            "reload_required": False,
            "changes_log": [],
        }

        with patch(
            "app.backend.services.llm_service.LLMService._call_graph_agent",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await client.post(
                "/api/v1/llm/process",
                json={"project_id": test_project.id, "message": "레벨 25"},
                headers=auth_headers,
            )

        result = await db_session.execute(
            select(ConversationLog).where(ConversationLog.project_id == test_project.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].user_input == "레벨 25"
        assert logs[0].success is True
        assert logs[0].intent == "modify_level"

    async def test_process_agent_error_returns_failure(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        """Agent에서 예외 발생 시 success=False, code=500 응답."""
        with patch(
            "app.backend.services.llm_service.LLMService._call_graph_agent",
            new_callable=AsyncMock,
            side_effect=Exception("Agent crashed"),
        ):
            resp = await client.post(
                "/api/v1/llm/process",
                json={"project_id": test_project.id, "message": "레벨 25"},
                headers=auth_headers,
            )

        # llm_service.process_chat이 내부에서 에러를 잡아 ProcessResponse로 반환
        data = resp.json()
        assert data["success"] is False
        assert data["code"] == 500


class TestConversationHistory:
    """GET /api/v1/llm/history/{project_id}"""

    async def test_history_empty(
        self, client: AsyncClient, auth_headers: dict, test_project: Project
    ):
        resp = await client.get(f"/api/v1/llm/history/{test_project.id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_history_with_logs(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        for i in range(3):
            log = ConversationLog(
                project_id=test_project.id,
                user_input=f"message {i}",
                agent_response=f"response {i}",
                intent="test",
                success=True,
                processing_time=0.5,
            )
            db_session.add(log)
        await db_session.commit()

        resp = await client.get(f"/api/v1/llm/history/{test_project.id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3

    async def test_history_pagination(
        self,
        client: AsyncClient,
        auth_headers: dict,
        test_project: Project,
        db_session: AsyncSession,
    ):
        for i in range(5):
            log = ConversationLog(
                project_id=test_project.id,
                user_input=f"message {i}",
                success=True,
                processing_time=0.1,
            )
            db_session.add(log)
        await db_session.commit()

        resp = await client.get(
            f"/api/v1/llm/history/{test_project.id}?limit=2&offset=0",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_history_forbidden(
        self, client: AsyncClient, other_auth_headers: dict, test_project: Project
    ):
        resp = await client.get(
            f"/api/v1/llm/history/{test_project.id}", headers=other_auth_headers
        )
        assert resp.status_code == 403

    async def test_history_not_found(self, client: AsyncClient, auth_headers: dict):
        resp = await client.get("/api/v1/llm/history/9999", headers=auth_headers)
        assert resp.status_code == 404
