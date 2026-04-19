"""Reader game_overview 전용 경로 — LLM 1 회로 게임 컨셉 요약.

Router 가 intent=game_overview 로 내려준 경우, Reader 가 _ReaderQuery LLM 파싱을
스킵하고 payload 수집 + 요약 LLM 을 호출한다.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from agent.editor.nodes.reader import (
    _collect_game_overview_payload,
    _fallback_game_overview,
    reader,
)


class TestCollectPayload:
    def test_structure(self):
        def fake_read(game_id, filename):
            if filename == "System.json":
                return {
                    "gameTitle": "테스트 게임",
                    "currencyUnit": "G",
                    "startingParty": [1, 2],
                    "elements": [None, "물리", "불", "물"],
                }
            if filename == "Actors.json":
                return [
                    None,
                    {"id": 1, "name": "해롤드"},
                    {"id": 2, "name": "테레즈"},
                ]
            if filename == "Enemies.json":
                return [None, {"id": 1, "name": "박쥐"}]
            if filename == "MapInfos.json":
                return [None, {"id": 1, "name": "시작마을"}]
            # 빈 파일
            return None

        with patch("agent.editor.nodes.reader.read_game_json", side_effect=fake_read):
            payload = _collect_game_overview_payload("g")

        assert payload["title"] == "테스트 게임"
        assert payload["currency"] == "G"
        assert payload["startingParty"] == [1, 2]
        assert payload["party_names"] == ["해롤드", "테레즈"]
        assert payload["actor_count"] == 2
        assert payload["enemy_count"] == 1
        assert payload["map_count"] == 1

    def test_empty_game_safe(self):
        """빈 game 에서도 크래시 없음."""
        with patch("agent.editor.nodes.reader.read_game_json", return_value=None):
            payload = _collect_game_overview_payload("g")
        # 대부분 키 없음 (정보 수집 실패) — party_names 는 항상 [] 로 세팅
        assert payload.get("party_names") == []
        assert "title" not in payload


class TestFallbackTemplate:
    def test_basic(self):
        payload = {
            "title": "드래곤 퀘스트",
            "party_names": ["영웅"],
            "actor_count": 3,
            "enemy_count": 5,
            "map_count": 2,
        }
        s = _fallback_game_overview(payload)
        assert "드래곤 퀘스트" in s
        assert "영웅" in s
        assert "3" in s or "5" in s  # count 포함

    def test_empty(self):
        s = _fallback_game_overview({})
        assert "제목 미정" in s


@pytest.mark.asyncio
async def test_reader_game_overview_skips_query_llm():
    """intent=game_overview 이면 _ReaderQuery 파싱 LLM 호출 없이 바로 요약."""
    state = {
        "intent": "game_overview",
        "user_input": "이 게임은 어떤 게임이야?",
        "game_id": "test",
    }

    def fake_read(game_id, filename):
        if filename == "System.json":
            return {"gameTitle": "T", "startingParty": []}
        return None

    with (
        patch("agent.editor.nodes.reader.read_game_json", side_effect=fake_read),
        patch(
            "agent.editor.nodes.reader.invoke_llm",
            new_callable=AsyncMock,
            return_value="이 게임은 T 입니다. 판타지 RPG 로 보입니다.",
        ) as mock_llm,
    ):
        result = await reader(state)

    # LLM 은 정확히 1 회 — game_overview 요약만
    assert mock_llm.await_count == 1
    assert "T" in result["final_response"] or "판타지" in result["final_response"]


@pytest.mark.asyncio
async def test_reader_query_intent_uses_query_parse_path():
    """intent=query 이면 기존 query 파싱 경로 (LLM 으로 _ReaderQuery 구조화)."""
    from agent.editor.nodes.reader import _ReaderQuery

    state = {
        "intent": "query",
        "user_input": "적 목록 보여줘",
        "game_id": "test",
    }

    def fake_read(game_id, filename):
        if filename == "Enemies.json":
            return [None, {"id": 1, "name": "슬라임"}]
        return None

    q = _ReaderQuery(
        query_type="bulk_list",
        entity_type="enemy",
        entity_name=None,
        field_name=None,
        reasoning="t",
    )

    with (
        patch("agent.editor.nodes.reader.read_game_json", side_effect=fake_read),
        patch(
            "agent.editor.nodes.reader.invoke_llm",
            new_callable=AsyncMock,
            return_value=q,
        ) as mock_llm,
    ):
        result = await reader(state)

    # game_overview 경로 아니므로 _ReaderQuery 파싱 LLM 호출
    assert mock_llm.await_count >= 1
    assert "final_response" in result
