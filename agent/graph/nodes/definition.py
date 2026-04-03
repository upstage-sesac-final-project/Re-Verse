"""Definition 노드 — 1단계: 핵심 키워드 추출."""

import logging
import os
import time
from typing import cast

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
from agent.utils.game_data_io import get_next_entity_id, get_system_context

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

        # 4. 파라미터 정제 (기존 ID 필드들을 대소문자 구분 없이 찾아서 추출)
        raw_params = mod.get("params", {})
        clean_params = {}
        llm_provided_id = None

        # ID로 추정되는 필드들 (id, Actor_id, actor_id 등)
        potential_id_keys = [
            "id",
            "target_id",
            id_field,
            f"{target}_id".lower(),
            f"{target}_id".capitalize(),
        ]

        for k, v in raw_params.items():
            # 대소문자 무시하고 ID 필드인지 확인
            is_id_field = any(k.lower() == p.lower() for p in potential_id_keys)
            if is_id_field:
                if v and v != "NEW":
                    llm_provided_id = v
            else:
                clean_params[k] = v

        # 5. ID 값 확정
        mapped_id = None
        target_name = clean_params.get("name")

        # UPDATE인 경우, LLM이 제공한 ID를 최우선으로 함 (이름이 바뀌었을 수 있으므로 이름 매핑보다 우선)
        if action_type == "update" and llm_provided_id is not None:
            final_id = llm_provided_id
        else:
            # 이름 기반 매핑 시도
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

            # UPDATE인데 여전히 NEW라면, 매핑되지 않은 대상을 수정하려 하는 것이므로
            # 분류 단계에서 찾았던 subject의 ID를 재검색 시도
            if action_type == "update" and final_id == "NEW":
                # classifications에서 "subject"에 해당하는 ID가 있는지 확인 (Step 1의 subject와 일치하는 name 찾기)
                # 여기서는 단순화를 위해 llm_provided_id가 없고 mapped_id도 없으면 일단 NEW 유지
                pass

        if action_type == "create" and not mapped_id:
            final_id = "NEW"

        clean_params[id_field] = final_id
        formatted_mods.append({"type": action_type, "target": target, "params": clean_params})

    return formatted_mods


async def definition(state: AgentState) -> dict:
    """사용자 입력에서 핵심 파라미터 추출(1단계) 후 최종 명세 생성(5단계) 수행."""
    game_id = state.get("game_id", "game_001")
    user_input = state.get("user_input", "")
    _t0 = time.perf_counter()

    logger.info("─── 🧩 Definition START ───────────────────────────────")

    logger.info("=" * 60)
    logger.info("[Definition] 노드 시작 - game_id: %s, user_input: %s", game_id, user_input)

    # --- [1단계: 핵심 키워드 추출] ---
    logger.info(f"[Definition] Step 1: '{user_input}'에서 키워드 추출 중...")
    messages_1 = build_step1_prompt(state)
    response_1 = cast(
        Step1ExtractionResponse,
        await invoke_llm(messages=messages_1, structured_output=Step1ExtractionResponse),
    )
    extractions = [ext.model_dump() for ext in response_1.extractions]
    logger.debug("[Definition] Step 1 완료 - 추출된 키워드 수: %d", len(extractions))

    # --- [2단계: 카테고리 분류] ---
    logger.info("[Definition] Step 2: 추출된 대상들 카테고리 분류 중...")
    messages_2 = build_step2_prompt(extractions)
    response_2 = cast(
        Step2ClassificationResponse,
        await invoke_llm(messages=messages_2, structured_output=Step2ClassificationResponse),
    )
    classifications = [cls.model_dump() for cls in response_2.classifications]
    logger.debug("[Definition] Step 2 완료 - 분류된 엔티티 수: %d", len(classifications))

    # --- [3단계: 파이썬 기반 시스템 문맥 보정 (비용 0)] ---
    # 결과물 중에 시스템 참조(system_ref)가 있을 때만 작동
    needs_system_info = any(cls.get("system_ref") is not None for cls in classifications)
    sys_info = {}

    if needs_system_info:
        logger.info("[Definition] Step 3: 시스템 정보 기반 보정 수행 중...")
        sys_info = get_system_context(game_id)

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
                logger.debug("[Definition] Step 3 보정: 주인공(hero) -> ID:%s", cls["mapped_id"])

            # 'game_title' 참조 보정
            elif ref == "game_title":
                cls["current_value"] = sys_info["gameTitle"]
                cls["reason"] += f" (현재 게임 제목: {sys_info['gameTitle']})"
                logger.debug("[Definition] Step 3 보정: 게임 제목 -> %s", cls["current_value"])

            # 'currency' 참조 보정
            elif ref == "currency":
                cls["current_value"] = sys_info["currencyUnit"]
                cls["reason"] += f" (현재 화폐 단위: {sys_info['currencyUnit']})"
                logger.debug("[Definition] Step 3 보정: 화폐 단위 -> %s", cls["current_value"])

    # 3.5단계: category_label 처리 (정리용)
    for cls in classifications:
        if cls.get("is_category_label"):
            logger.info("[Definition] 카테고리 지칭어 감지: %s -> %s", cls["name"], cls["category"])

    # --- [4단계: 구체적 ID 매핑 (RAG 검색)] ---
    logger.info("[Definition] Step 4: 엔티티 ID 매핑 중...")
    from difflib import SequenceMatcher

    retriever = RPGRetriever(game_id)
    if not sys_info:  # 시스템 정보 미리 확보
        sys_info = get_system_context(game_id)

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
                logger.debug(
                    "[Definition] Step 4 속성 매핑 성공: %s -> ID:%s", cls["name"], best_id
                )
            else:
                cls["mapped_id"] = "NEW"
                cls["reason"] += " (새로운 속성으로 판단)"
                logger.debug("[Definition] Step 4 속성 신규 생성 판단: %s", cls["name"])
            continue

        # [일반 케이스: 파일 기반 검색]
        plural_cat = _normalize_category_to_plural(cls["category"])
        results = await retriever.retrieve_entities(cls["name"], plural_cat, k=1)

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
                    logger.debug(
                        "[Definition] Step 4 중복 이름 발견: %s -> ID:%s",
                        cls["name"],
                        cls["mapped_id"],
                    )
                else:
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += (
                        f" (새로운 이름으로 판단: {best_match['name']}와 유사도 {similarity:.2f}로 낮음)"
                    )
                    logger.debug(
                        "[Definition] Step 4 신규 생성(낮은 유사도): %s (vs %s: %.2f)",
                        cls["name"],
                        best_match["name"],
                        similarity,
                    )
            else:
                if similarity >= 0.5:
                    cls["mapped_id"] = best_match["id"]
                    cls["actual_name"] = best_match["name"]
                    cls["reason"] += f" (매칭 성공: {best_match['name']} ID:{best_match['id']})"
                    logger.debug(
                        "[Definition] Step 4 매칭 성공: %s -> ID:%s (유사도 %.2f)",
                        cls["name"],
                        cls["mapped_id"],
                        similarity,
                    )
                else:
                    # [능동적 생성] 수정/조회인데 대상을 못 찾으면 NEW로 간주하여 생성을 유도
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += (
                        f" (데이터를 찾을 수 없어 신규 생성으로 전환: {best_match['name']}와 유사도 {similarity:.2f}로 낮음)"
                    )
                    logger.debug(
                        "[Definition] Step 4 매칭 실패(신규 생성 전환): %s (vs %s: %.2f)",
                        cls["name"],
                        best_match["name"],
                        similarity,
                    )
        else:
            # 검색 결과가 아예 없는 경우
            cls["mapped_id"] = "NEW"
            cls["reason"] += " (데이터가 존재하지 않아 신규 생성 대상으로 지정)"
            logger.debug("[Definition] Step 4 검색 결과 없음(신규): %s", cls["name"])

    # 로그 출력
    for ext in extractions:
        logger.info(
            "[Definition] 추출 결과: [%s] %s (속성: %s, 값: %s)",
            ext["action"],
            ext["subject"],
            ext["property"],
            ext["value"],
        )
    for cls in classifications:
        mapped_str = f" -> ID:{cls.get('mapped_id')}" if cls.get("mapped_id") else ""
        scores = cls.get("category_scores", {})
        top_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
        scores_str = ", ".join([f"{k}:{v:.1f}" for k, v in top_scores])
        logger.info(
            "[Definition] 분류 결과: %s%s -> %s (Scores: %s)",
            cls["name"],
            mapped_str,
            cls["category"],
            scores_str,
        )
        logger.debug("[Definition] 분류 사유: %s", cls["reason"])

    # --- [4.5단계: 중복 및 지칭어 필터링] ---
    # 동일 카테고리에 구체적인 이름이 있는 엔티티와 '지칭어'가 섞여있으면 지칭어 제거
    final_classifications = []
    categories_with_real_names = {
        cls["category"] for cls in classifications if not cls.get("is_category_label")
    }

    for cls in classifications:
        # 지칭어인데 해당 카테고리에 이미 구체적인 이름의 엔티티가 있다면 제외
        if cls.get("is_category_label") and cls["category"] in categories_with_real_names:
            logger.info(
                "[Definition] 중복 지칭어 제거: %s (카테고리 %s에 구체적 대상 존재)",
                cls["name"],
                cls["category"],
            )
            continue
        final_classifications.append(cls)

    # --- [5단계: 최종 조립 (Specification)] ---
    logger.info("[Definition] Step 5: 최종 수정 명세 생성 중...")

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
    logger.debug("[Definition] Step 5 완료 - 대상 파일: %s", final_response.target_files)

    # --- [규격 강제 보정 로직 호출] ---
    logger.info("[Definition] Step 6: 규격 준수 여부 확인 및 보정 중...")
    strictly_formatted_mods = _format_to_progress_spec(
        final_response.modifications, classifications
    )

    # --- [상태 전이용 ID 맵핑 강화 및 중복 제거] ---
    final_extracted_ids = {}
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
    logger.info("[Definition] Step 7: 신규 생성 대상 ID 할당 중...")
    next_id_cache = {}

    for mod in strictly_formatted_mods:
        target = mod["target"]
        id_field = CATEGORY_TO_ID_FIELD.get(target, f"{target}_id")
        action_type = mod.get("type")
        params = mod.get("params", {})

        if action_type == "create" or params.get(id_field) == "NEW":
            if target not in next_id_cache:
                next_id_cache[target] = get_next_entity_id(game_id, target)

            assigned_id = next_id_cache[target]
            params[id_field] = assigned_id
            display_name = params.get("name", target)
            final_extracted_ids[display_name] = assigned_id
            logger.info(
                "[Definition] 신규 ID 할당: [%s] %s -> ID:%s", target, display_name, assigned_id
            )
            # 다음 생성을 위해 ID 증가 (한 번에 여러 개 생성 대비)
            next_id_cache[target] += 1

    logger.info("[Definition] 노드 완료 - 생성된 modification 수: %d", len(strictly_formatted_mods))
    # 최종 결과 반환
    result = {
        "target_files": final_response.target_files,
        "modifications": strictly_formatted_mods,
        "extracted_ids": final_extracted_ids,
        "params_sufficient": final_response.params_sufficient,
        # "final_response": final_response.message_for_user,
    }
    logger.info(
        "─── ✅ Definition END (elapsed=%.2fs, targets=%d, mods=%d, ids=%d, params_ok=%s) ──",
        time.perf_counter() - _t0,
        len(final_response.target_files),
        len(strictly_formatted_mods),
        len(final_extracted_ids),
        final_response.params_sufficient,
    )
    return result
