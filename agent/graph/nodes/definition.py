"""Definition 노드 — 1단계: 핵심 키워드 추출."""

import json
import logging
import os
from typing import Any, cast

from agent.core.llm_client import invoke_llm
from agent.graph.schemas import (
    FinalDefinitionResponse,
    Step1ExtractionResponse,
    Step2ClassificationResponse,
)
from agent.graph.state import AgentState
from agent.prompts.definition_prompt import (
    build_step1_prompt,
    build_step2_prompt,
    build_step5_prompt,
)
from agent.rag.retriever import RPGRetriever

logger = logging.getLogger(__name__)

# --- 공통 매핑 상수 ---
CATEGORY_TO_PLURAL = {
    "actor": "Actors",
    "enemy": "Enemies",
    "item": "Items",
    "skill": "Skills",
    "weapon": "Weapons",
    "armor": "Armors",
    "class": "Classes",
    "state": "States",
    "element": "System",  # 속성은 System.json 내에 포함됨
    "system": "System",
}

CATEGORY_TO_ID_FIELD = {
    "actor": "actor_id",
    "enemy": "enemy_id",
    "item": "item_id",
    "skill": "skill_id",
    "weapon": "weapon_id",
    "armor": "armor_id",
    "class": "class_id",
    "state": "state_id",
    "element": "element_id",
    "system": "system_id",
}

# 복수형(파일명/폴더명) -> 단수형(내부 타겟명) 변환용
PLURAL_TO_SINGULAR = {v.lower(): k for k, v in CATEGORY_TO_PLURAL.items()}
# 특수 케이스 추가
PLURAL_TO_SINGULAR.update({"enemies": "enemy", "actors": "actor"})


def _normalize_category_to_plural(cat: str) -> str:
    """단수형 카테고리를 RPG Maker MZ 파일용 복수형으로 변환 (예: Enemy -> Enemies)"""
    return CATEGORY_TO_PLURAL.get(cat.lower(), cat.capitalize())


def _get_next_id(game_id: str, category: str) -> int:
    """특정 카테고리의 다음 가용한 ID(마지막 ID + 1)를 가져온다."""
    data_dir = os.path.join("storage", "games", game_id, "data")
    plural_cat = _normalize_category_to_plural(category)
    file_path = os.path.join(data_dir, f"{plural_cat}.json")

    if not os.path.exists(file_path):
        return 1

    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            if not isinstance(data, list):
                return 1
            # RPG Maker 데이터는 보통 [null, {id:1}, {id:2}, ...] 구조임
            ids = [item["id"] for item in data if isinstance(item, dict) and "id" in item]
            return max(ids) + 1 if ids else 1
    except Exception:
        return 1


def _get_system_info(game_id: str) -> dict:
    """System.json 및 Actors.json에서 핵심 시스템 정보를 추출한다."""
    data_dir = os.path.join("storage", "games", game_id, "data")
    system_path = os.path.join(data_dir, "System.json")
    actors_path = os.path.join(data_dir, "Actors.json")

    info: dict[str, Any] = {
        "gameTitle": "알 수 없음",
        "currencyUnit": "G",
        "hero": {"id": None, "name": "알 수 없음"},
        "startPosition": {"mapId": 0, "x": 0, "y": 0},
        "elements": [],  # 속성 리스트 추가
    }

    if os.path.exists(system_path):
        try:
            with open(system_path, encoding="utf-8") as f:
                sys_data = json.load(f)
                info["gameTitle"] = sys_data.get("gameTitle", "알 수 없음")
                info["currencyUnit"] = sys_data.get("currencyUnit", "G")
                info["elements"] = sys_data.get("elements", [])
                info["startPosition"] = {
                    "mapId": sys_data.get("startMapId", 0),
                    "x": sys_data.get("startX", 0),
                    "y": sys_data.get("startY", 0),
                }
                # 주인공 (1번 파티원) ID
                party = list(sys_data.get("partyMembers", []))
                if party:
                    info["hero"]["id"] = party[0]
        except Exception:
            pass
    # ... (생략된 이름 찾기 로직 유지)

    # 주인공 이름 찾기 (Actors.json)
    if info["hero"]["id"] and os.path.exists(actors_path):
        try:
            with open(actors_path, encoding="utf-8") as f:
                actors_data = json.load(f)
                for a in actors_data:
                    if a and a.get("id") == info["hero"]["id"]:
                        info["hero"]["name"] = a.get("name", "알 수 없음")
                        break
        except Exception:
            pass

    return info


def _format_to_progress_spec(modifications: list[dict], classifications: list[dict]) -> list[dict]:
    """LLM의 출력을 PROGRESS.md 규격에 맞게 강제로 교정한다."""
    formatted_mods = []

    # 허용된 액션 목록
    valid_actions = ["read", "update", "create", "delete"]

    for mod in modifications:
        # 1. 타입과 타겟 추출 및 교정
        raw_type = str(mod.get("type", "update")).lower()
        raw_target = str(mod.get("target", "unknown")).lower()

        # 만약 type에 카테고리가 들어오고 target에 이름이 들어왔을 경우 교정 시도
        if raw_type not in valid_actions:
            if raw_target in valid_actions:
                action_type = raw_target
                target_cat = raw_type
            else:
                action_type = "update"
                target_cat = raw_type
        else:
            action_type = raw_type
            target_cat = raw_target

        # 2. 타겟 카테고리 정규화
        target = PLURAL_TO_SINGULAR.get(target_cat, target_cat)
        if target == target_cat and target.endswith("s") and len(target) > 1:
            target = target[:-1]

        # 3. 해당 타겟의 ID 필드명 결정
        id_field = CATEGORY_TO_ID_FIELD.get(target, f"{target}_id")

        # 4. 파라미터 정제
        raw_params = mod.get("params", {})
        clean_params = {}
        for k, v in raw_params.items():
            if k not in ["id", "target_id", id_field]:
                clean_params[k] = v

        # 5. ID 값 확정
        llm_provided_id = raw_params.get(id_field) or raw_params.get("id")
        if llm_provided_id == "NEW":
            llm_provided_id = None

        target_name = clean_params.get("name")
        mapped_id = None

        for cls in classifications:
            if target_name and (cls["name"] == target_name or target_name in cls["name"]):
                mapped_id = cls.get("mapped_id")
                break

        if mapped_id is None:
            category_matches = [
                cls for cls in classifications if cls["category"].lower() == target.lower()
            ]
            if len(category_matches) == 1:
                mapped_id = category_matches[0].get("mapped_id")

        final_id = mapped_id or llm_provided_id or "NEW"
        if action_type == "create" and not mapped_id:
            final_id = "NEW"

        clean_params[id_field] = final_id
        formatted_mods.append({"type": action_type, "target": target, "params": clean_params})

    return formatted_mods


async def definition(state: AgentState) -> dict:
    """사용자 입력에서 핵심 파라미터 추출(1단계) 후 최종 명세 생성(5단계) 수행."""
    # ... (기존 1~4단계 로직 유지)
    print("\n[Step 2] Definition 노드 진입")

    game_id = state.get("game_id", "game_001")
    user_input = state.get("user_input", "")

    # --- [1단계: 핵심 키워드 추출] ---
    print(f"[*] 1단계: '{user_input}'에서 키워드 추출 중...")
    messages_1 = build_step1_prompt(state)
    response_1 = cast(
        Step1ExtractionResponse,
        await invoke_llm(messages=messages_1, structured_output=Step1ExtractionResponse),
    )
    extractions = [ext.dict() for ext in response_1.extractions]

    # --- [2단계: 카테고리 분류] ---
    print("[*] 2단계: 추출된 대상들 카테고리 분류 중...")
    messages_2 = build_step2_prompt(extractions)
    response_2 = cast(
        Step2ClassificationResponse,
        await invoke_llm(messages=messages_2, structured_output=Step2ClassificationResponse),
    )
    classifications = [cls.dict() for cls in response_2.classifications]

    # --- [3단계: 파이썬 기반 시스템 문맥 보정 (비용 0)] ---
    # 결과물 중에 시스템 참조(system_ref)가 있을 때만 작동
    needs_system_info = any(cls.get("system_ref") is not None for cls in classifications)

    if needs_system_info:
        print("[*] 3단계: 시스템 정보 기반 보정 수행 중...")
        sys_info = _get_system_info(game_id)

        for cls in classifications:
            ref = cls.get("system_ref")
            if not ref:
                continue

            # 'hero' (주인공) 참조 보정
            if ref == "hero":
                cls["mapped_id"] = sys_info["hero"]["id"]
                cls["actual_name"] = sys_info["hero"]["name"]
                cls["reason"] += (
                    f" (시스템 주인공: {sys_info['hero']['name']} ID:{sys_info['hero']['id']})"
                )

            # 'game_title' 참조 보정
            elif ref == "game_title":
                cls["current_value"] = sys_info["gameTitle"]
                cls["reason"] += f" (현재 게임 제목: {sys_info['gameTitle']})"

            # 'currency' 참조 보정
            elif ref == "currency":
                cls["current_value"] = sys_info["currencyUnit"]
                cls["reason"] += f" (현재 화폐 단위: {sys_info['currencyUnit']})"

    # 3.5단계: category_label 처리 (정리용)
    for cls in classifications:
        if cls.get("is_category_label"):
            print(f"  - [카테고리 지칭어 감지] {cls['name']} -> {cls['category']}")

    # --- [4단계: 구체적 ID 매핑 (RAG 검색)] ---
    print("[*] 4단계: 엔티티 ID 매핑 중...")
    from difflib import SequenceMatcher

    retriever = RPGRetriever(game_id)
    sys_info = _get_system_info(game_id)  # 시스템 정보 미리 확보

    for cls in classifications:
        # 이미 3단계에서 ID를 찾았거나, 분류가 None이거나, 카테고리 지칭어면 패스
        if cls.get("mapped_id") or cls["category"] == "None" or cls.get("is_category_label"):
            if cls.get("is_category_label"):
                cls["reason"] += " (카테고리 지칭어 - 검색 생략)"
            continue

        # [특수 케이스: Element (속성)]
        if cls["category"] == "Element":
            best_id = None
            max_sim = 0.0
            # System.json의 elements 배열에서 검색 (보통 ["", "물리", "불", ...])
            for i, el_name in enumerate(sys_info.get("elements", [])):
                if not el_name:
                    continue
                sim = SequenceMatcher(None, cls["name"], el_name).ratio()
                if sim > max_sim:
                    max_sim = sim
                    best_id = i

            if best_id is not None and max_sim >= 0.5:
                cls["mapped_id"] = best_id
                cls["actual_name"] = sys_info["elements"][best_id]
                cls["reason"] += (
                    f" (시스템 속성 일치: {cls['actual_name']} ID:{best_id} 유사도:{max_sim:.2f})"
                )
            else:
                cls["mapped_id"] = "NEW"
                cls["reason"] += " (새로운 속성으로 판단)"
            continue

        # [일반 케이스: 파일 기반 검색]
        plural_cat = _normalize_category_to_plural(cls["category"])
        results = retriever.retrieve_entities(cls["name"], plural_cat, k=1)

        # 1단계 의도 확인 (CREATE 인지 여부)
        is_create = any(
            ext["action"] == "CREATE"
            and (ext["subject"] == cls["name"] or ext["value"] == cls["name"])
            for ext in extractions
        )

        if results:
            best_match = results[0]
            # 글자 모양 유사도 체크
            similarity = SequenceMatcher(None, cls["name"], best_match["name"]).ratio()

            # [매칭 정책]
            # 1. 생성(CREATE)인 경우: 글자 모양이 거의 똑같을 때(0.9)만 중복으로 간주하고 ID 할당. 아니면 NEW.
            # 2. 수정/조회인 경우: 의미 기반 검색 결과를 믿고 ID 할당 (유사도 0.5 이상이면 허용)

            if is_create:
                if similarity >= 0.9:
                    cls["mapped_id"] = best_match["id"]
                    cls["actual_name"] = best_match["name"]
                    cls["reason"] += (
                        f" (중복 이름 발견: {best_match['name']} ID:{best_match['id']})"
                    )
                else:
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += (
                        f" (새로운 이름으로 판단: {best_match['name']}와 유사도 {similarity:.2f}로 낮음)"
                    )
            else:
                if similarity >= 0.5:
                    cls["mapped_id"] = best_match["id"]
                    cls["actual_name"] = best_match["name"]
                    cls["reason"] += f" (매칭 성공: {best_match['name']} ID:{best_match['id']})"
                else:
                    # [능동적 생성] 수정/조회인데 대상을 못 찾으면 NEW로 간주하여 생성을 유도
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += (
                        f" (데이터를 찾을 수 없어 신규 생성으로 전환: {best_match['name']}와 유사도 {similarity:.2f}로 낮음)"
                    )
        else:
            # 검색 결과가 아예 없는 경우
            cls["mapped_id"] = "NEW"
            cls["reason"] += " (데이터가 존재하지 않아 신규 생성 대상으로 지정)"

    # 로그 출력
    for ext in extractions:
        print(
            f"  - 추출: [{ext['action']}] {ext['subject']} (속성: {ext['property']}, 값: {ext['value']})"
        )
    for cls in classifications:
        mapped_str = f" -> ID:{cls.get('mapped_id')}" if cls.get("mapped_id") else ""

        # 점수 상위 3개 추출 (로그용)
        scores = cls.get("category_scores", {})
        top_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        scores_str = ", ".join([f"{k}:{v:.1f}" for k, v in top_scores])

        print(f"  - 분류: {cls['name']}{mapped_str} -> {cls['category']} (Scores: {scores_str})")
        print(f"    ㄴ 사유: {cls['reason']}")

    # 4. 상태 업데이트
    # return {
    #     "step1_extractions": extractions,
    #     "step2_classifications": classifications,
    #     "thought_process": f"1단계: {response_1.thought_process}\n2단계: {response_2.thought_process}",
    #     "params_sufficient": params_sufficient,
    # }

    # --- [4.5단계: 중복 및 지칭어 필터링] ---
    # 동일 카테고리에 구체적인 이름이 있는 엔티티와 '지칭어'가 섞여있으면 지칭어 제거
    final_classifications = []
    categories_with_real_names = {
        cls["category"] for cls in classifications if not cls.get("is_category_label")
    }

    for cls in classifications:
        # 지칭어인데 해당 카테고리에 이미 구체적인 이름의 엔티티가 있다면 제외
        if cls.get("is_category_label") and cls["category"] in categories_with_real_names:
            print(
                f"  - [중복 지칭어 제거] {cls['name']} (카테고리 {cls['category']}에 구체적 대상 존재)"
            )
            continue
        final_classifications.append(cls)

    # --- [5단계: 최종 조립 (Specification)] ---
    print("[*] 5단계: 최종 수정 명세 생성 중...")

    # 스키마 파일 로드 (로컬 비용 0)
    schema_dir = os.path.join("agent", "rag", "data")
    schema1_path = os.path.join(schema_dir, "rpgmaker-mz-data-schema.md")
    schema2_path = os.path.join(schema_dir, "rpgmaker-mz-data-schema2.md")

    schema1_content = ""
    schema2_content = ""
    if os.path.exists(schema1_path):
        with open(schema1_path, encoding="utf-8") as f:
            schema1_content = f.read()
    if os.path.exists(schema2_path):
        with open(schema2_path, encoding="utf-8") as f:
            schema2_content = f.read()

    messages_5 = build_step5_prompt(
        state, extractions, final_classifications, sys_info, schema1_content, schema2_content
    )

    final_response = cast(
        FinalDefinitionResponse,
        await invoke_llm(messages=messages_5, structured_output=FinalDefinitionResponse),
    )

    # --- [규격 강제 보정 로직 호출] ---
    print("[*] 6단계: 규격 준수 여부 최종 확인 및 보정 중...")
    strictly_formatted_mods = _format_to_progress_spec(
        final_response.modifications, classifications
    )

    # --- [상태 전이용 ID 맵핑 강화 및 중복 제거] ---
    final_extracted_ids = {}

    # 1. LLM이 명시적으로 반환한 ID들 먼저 수집
    if final_response.extracted_ids:
        for k, v in final_response.extracted_ids.items():
            if v and v != "NEW":
                final_extracted_ids[k] = v

    # 2. 분류 단계에서 확정된 ID들 병합 (system_ref 우선)
    for cls in classifications:
        m_id = cls.get("mapped_id")
        if m_id and m_id != "NEW":
            # system_ref가 있으면 그것을 키로 사용 (중복 방지용 메인 키)
            if cls.get("system_ref"):
                final_extracted_ids[cls["system_ref"]] = m_id

            # 원문 이름 추가 (해당 ID가 이미 다른 키로 저장되어 있더라도 검색 편의를 위해 추가)
            if cls["name"] not in final_extracted_ids:
                final_extracted_ids[cls["name"]] = m_id

    # --- [7단계: 신규 ID 실제 할당 (NEW -> Last ID + 1)] ---
    print("[*] 7단계: 신규 생성 대상 ID 할당 중...")
    next_id_cache = {}

    for mod in strictly_formatted_mods:
        target = mod["target"]
        id_field = CATEGORY_TO_ID_FIELD.get(target, f"{target}_id")

        params = mod.get("params", {})
        if params.get(id_field) == "NEW":
            if target not in next_id_cache:
                next_id_cache[target] = _get_next_id(game_id, target)

            assigned_id = next_id_cache[target]
            params[id_field] = assigned_id

            # extracted_ids에도 반영
            name = params.get("name", target)
            final_extracted_ids[name] = assigned_id

            # 다음 생성을 위해 ID 증가 (한 번에 여러 개 생성 대비)
            next_id_cache[target] += 1

    # 최종 결과 반환
    return {
        "target_files": final_response.target_files,
        "modifications": strictly_formatted_mods,
        "extracted_ids": final_extracted_ids,
        "params_sufficient": final_response.params_sufficient,
        "final_response": final_response.message_for_user,
    }
