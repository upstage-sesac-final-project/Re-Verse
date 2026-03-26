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

def _normalize_category(category: str) -> str:
    """카테고리명(예: Actors, Enemies)을 단수형(예: actor, enemy)으로 정규화한다."""
    if not category:
        return "unknown"
    cat = category.lower()
    if cat == "classes":
        return "class"
    if cat == "enemies":
        return "enemy"
    if cat.endswith("s"):
        return cat[:-1]
    return cat

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
        retrieved_context += f"\n### [{cat} 정보]\n- 신규 생성 시(CREATE) 사용할 ID: {next_id}\n"
        if results:
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


    # 5. 결과 후처리 (표준화된 형식으로 변환)

    formatted_mods = []
    extracted_ids = {}
    target_files = set()

    for mod in response.modifications:
        target_files.add(mod.file)
        
        # 카테고리 정규화 (Actors -> actor)
        cat_type = _normalize_category(mod.target_entity.category)
        
        # ID 추출 및 캐싱 (extracted_ids용)
        t_id = mod.target_entity.id
        if t_id and t_id != "NEW":
            # 숫자 형태면 int로 변환하여 저장
            extracted_ids[f"{cat_type}_id"] = int(t_id) if str(t_id).isdigit() else t_id

        # Params 구성 (PROGRESS.md 규격: target_id, name, field: value)
        mod_params = {
            f"{cat_type}_id": t_id,
            "name": mod.target_entity.name
        }
        
        # 수정/조회할 구체적 필드가 있는 경우 추가
        if mod.target_field:
            mod_params[mod.target_field] = mod.new_value
        
        # 보조 객체가 있는 경우 (예: 추가할 스킬 ID 등)
        if mod.action_object:
            obj_cat = _normalize_category(mod.action_object.category)
            mod_params[f"{obj_cat}_id"] = mod.action_object.id
            if mod.action_object.id and mod.action_object.id != "NEW":
                extracted_ids[f"{obj_cat}_id"] = int(mod.action_object.id) if str(mod.action_object.id).isdigit() else mod.action_object.id

        # 최종 리스트 추가
        formatted_mods.append({
            "type": mod.action.lower(),  # create, update, read, delete
            "target": cat_type,
            "params": mod_params
        })

    print(f"[*] 분석 완료: {len(formatted_mods)}개의 작업 식별됨.")

    # 6. 최종 상태 업데이트
    return {
        "target_files": list(target_files),
        "modifications": formatted_mods,      # 규격화된 수정 목록
        "execution_plan": formatted_mods,     # Executor(3번 노드)가 읽을 입력값
        "extracted_ids": extracted_ids,       # 추출된 ID 맵
        "params_sufficient": response.params_sufficient,
        "final_response": response.message_for_user if not response.params_sufficient else None
    }