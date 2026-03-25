"""Definition 노드 — 2단계: Multi-Step & Dependency 대응."""

import json
import logging
import os
from typing import Any, cast

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.definition_prompt import build_prompt
from agent.rag.knowledge_retriever import knowledge_retriever
from agent.rag.retriever import RPGRetriever
from app.backend.schemas.rpgmaker import FinalDefinitionResponse

logger = logging.getLogger(__name__)

def _get_actual_value(game_id: str, category: str, target_id: Any, field: str) -> Any:
    """실제 JSON 파일에서 현재 값을 조회한다."""
    if not target_id or target_id == "NEW":
        return None

    filename = f"{category}.json"
    file_path = os.path.join("storage", "games", game_id, "data", filename)

    if not os.path.exists(file_path):
        return None

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            data_map = {item["id"]: item for item in data if item is not None}

        item = data_map.get(int(target_id))
        if item and field in item:
            return item[field]
        return None
    except Exception:
        return None

def _get_next_id(game_id: str, category: str) -> int:
    """JSON 파일에서 현재 최대 ID를 찾아 다음 ID를 반환한다."""
    filename = f"{category}.json"
    file_path = os.path.join("storage", "games", game_id, "data", filename)

    if not os.path.exists(file_path):
        return 1

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            ids = [item["id"] for item in data if item is not None and "id" in item]
            return max(ids) + 1 if ids else 1
    except Exception:
        return 1

async def definition(state: AgentState) -> dict:
    """사용자 입력과 의도를 바탕으로 구체적인 수정 대상 목록을 정의한다."""
    print("\n[Step 2] Definition 노드 진입")

    game_id = state.get("game_id", "game_001")
    user_input = state.get("user_input", "")
    intent = state.get("intent", "게임_요소_수정")

    # 1. RAG 인프라 준비
    retriever = RPGRetriever(game_id)

    # 2. Track A: 기술 지식 검색
    knowledge_context = knowledge_retriever.retrieve_knowledge(user_input + " " + intent)

    # 3. Track B: 모든 주요 카테고리 정보 확보 (Classes 추가)
    search_categories = ["Actors", "Classes", "Skills", "Items", "Enemies", "Weapons", "Armors"]
    retrieved_context = ""
    for cat in search_categories:
        next_id = _get_next_id(game_id, cat)
        results = retriever.retrieve_entities(user_input, cat, k=3)
        retrieved_context += f"\n### [{cat} 정보]\n- 신규 ID: {next_id}\n"
        if results:
            retrieved_context += "- 기존 데이터: " + ", ".join([f"{r['name']}(ID:{r['id']})" for r in results]) + "\n"

    # 4. 프롬프트 생성
    messages = build_prompt(state, knowledge_context, retrieved_context)

    # 5. LLM 호출 (Structured Output)
    print("[*] LLM 호출 중 (복합 작업 분석)...")

    response = cast(FinalDefinitionResponse, await invoke_llm(
        messages=messages,
        structured_output=FinalDefinitionResponse
    ))


    # 5. 결과 후처리 (현재 값 조회 등)

    modifications = []
    for mod in response.modifications:
        mod_dict = mod.model_dump()
        t_id = mod_dict.get("target_entity", {}).get("id")
        t_cat = mod_dict.get("target_entity", {}).get("category")
        t_field = mod_dict.get("target_field")

        if t_id and t_cat and t_field and t_id != "NEW":
            mod_dict["current_value"] = _get_actual_value(game_id, t_cat, t_id, t_field)
        modifications.append(mod_dict)

    print(f"[*] 분석 완료: {len(modifications)}개의 작업 식별됨.")

    # 6. 상태 업데이트
    return {
        "target_files": list(set([m["file"] for m in modifications])),
        "modifications": modifications,
        "extracted_ids": {
            "target_ids": [m["target_entity"]["id"] for m in modifications]
        },
        "params_sufficient": response.params_sufficient,
        "final_response": response.message_for_user if not response.params_sufficient else None
    }