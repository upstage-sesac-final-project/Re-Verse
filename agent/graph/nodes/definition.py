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
    if not target_id or target_id == "NEW" or not field:
        return None

    field = field.strip()
    # 카테고리 이름을 기반으로 파일명 후보 생성
    cat_name = category[0].upper() + category[1:] if category else ""
    filenames = [f"{cat_name}.json", f"{category}.json", f"{category.lower()}.json"]
    
    data = None
    actual_filename = None
    for fname in filenames:
        file_path = os.path.join("storage", "games", game_id, "data", fname)
        if os.path.exists(file_path):
            try:
                with open(file_path, encoding="utf-8") as f:
                    data = json.load(f)
                    actual_filename = fname
                    break
            except Exception:
                continue
    
    if data is None:
        print(f"  [Lookup Error] 파일을 찾을 수 없음: {filenames}")
        return None

    try:
        # ID 매핑 (문자열/숫자 모두 대응)
        data_map = {str(item["id"]): item for item in data if item is not None and "id" in item}
        item = data_map.get(str(target_id))
        
        if not item:
            print(f"  [Lookup Error] {actual_filename} 내 ID {target_id} 없음 (목록: {list(data_map.keys())[:5]}...)")
            return None

        # 배열 인덱스 처리 (예: params[0], 공백 허용)
        if "[" in field and field.endswith("]"):
            import re
            match = re.match(r"(\w+)\s*\[\s*(\d+)\s*\]", field)
            if match:
                base_field, index = match.groups()
                index = int(index)
                if base_field in item and isinstance(item[base_field], list):
                    if index < len(item[base_field]):
                        val = item[base_field][index]
                        print(f"  [Lookup Success] {actual_filename}[{target_id}].{base_field}[{index}] = {val}")
                        return val
                    else:
                        print(f"  [Lookup Error] 인덱스 범위 초과: {index} (길이: {len(item[base_field])})")
        
        # 일반 필드 처리
        val = item.get(field)
        print(f"  [Lookup Success] {actual_filename}[{target_id}].{field} = {val}")
        return val
    except Exception as e:
        print(f"  [Lookup Exception] {e}")
        logger.error(f"[Lookup] Error: {e}")
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
        # 검색 정확도를 위해 k를 조금 늘리고, 결과가 없으면 명시적으로 표시
        results = retriever.retrieve_entities(user_input, cat, k=3)
        retrieved_context += f"\n### [{cat} 정보]\n- 신규 생성 시(CREATE) 사용할 ID: {next_id}\n"
        if results:
            # 이름, ID와 함께 설명(있는 경우)을 포함하여 LLM의 판단을 도움
            items_str = []
            for r in results:
                info = f"{r['name']}(ID:{r['id']})"
                if r.get('description'):
                    info += f" - 설명: {r['description'][:20]}..."
                items_str.append(info)
            retrieved_context += "- 기존 데이터(ID 찾기용): " + ", ".join(items_str) + "\n"
        else:
            retrieved_context += "- 기존 데이터: (검색 결과 없음)\n"

    retrieved_context += "\n**주의**: 사용자가 언급한 대상이 '기존 데이터' 목록에 없다면, 함부로 ID를 추측하지 말고 `params_sufficient=False`와 함께 사용자에게 확인을 요청하십시오.\n"

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