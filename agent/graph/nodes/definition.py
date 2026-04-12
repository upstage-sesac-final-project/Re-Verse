"""Definition 노드 — 1단계: 핵심 키워드 추출."""

import logging
import os
import time
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
from agent.rag.vectorstore import vector_store
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

SUPPORTED_BULK_TARGETS = {
    "actor": {"target_file": "Actors.json", "rag_category": "Actors"},
    "enemy": {"target_file": "Enemies.json", "rag_category": "Enemies"},
    "item": {"target_file": "Items.json", "rag_category": "Items"},
    "weapon": {"target_file": "Weapons.json", "rag_category": "Weapons"},
    "armor": {"target_file": "Armors.json", "rag_category": "Armors"},
    "class": {"target_file": "Classes.json", "rag_category": "Classes"},
    "state": {"target_file": "States.json", "rag_category": "States"},
    "element": {"target_file": "System.json", "rag_category": None},
}
UNSUPPORTED_BULK_TARGETS = {"skill"}


def filter_category_labels(classifications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """지칭어(is_category_label)와 구체 이름이 섞여 있을 때 지칭어를 제거한다.

    규칙:
    1. 구체 이름(non-label)이 하나라도 있으면, 모든 카테고리 지칭어를 제거한다.
       예: "루시퍼 액터 추가" → '루시퍼'는 유지, '액터'(지칭어)는 제거.
    2. 동일 카테고리에 구체 이름과 지칭어가 공존하면, 지칭어를 제거한다.
    3. 지칭어만 있으면(예: "액터 전부 삭제") 그대로 유지한다.
    """
    categories_with_real_names = {
        cls["category"] for cls in classifications if not cls.get("is_category_label")
    }
    has_non_label_entity = any(not c.get("is_category_label") for c in classifications)

    result: list[dict[str, Any]] = []
    for cls in classifications:
        if cls.get("is_category_label") and has_non_label_entity:
            logger.info(
                "[Definition] 구체 대상이 있어 카테고리 지칭어 분류 제외: %s",
                cls.get("name"),
            )
            continue
        if cls.get("is_category_label") and cls["category"] in categories_with_real_names:
            logger.info(
                "[Definition] 중복 지칭어 제거: %s (카테고리 %s에 구체적 대상 존재)",
                cls["name"],
                cls["category"],
            )
            continue
        result.append(cls)
    return result


def _normalize_category_to_plural(cat: str) -> str:
    """단수형 카테고리를 RPG Maker MZ 파일용 복수형으로 변환 (예: Enemy -> Enemies)"""
    return CATEGORY_TO_PLURAL.get(cat.lower(), cat.capitalize())


def _normalize_target_category(cat: str) -> str:
    """카테고리명을 내부 target 규격(단수형 소문자)으로 정규화한다."""
    normalized = PLURAL_TO_SINGULAR.get(cat.lower(), cat.lower())
    if normalized == cat.lower() and normalized.endswith("s") and len(normalized) > 1:
        normalized = normalized[:-1]
    return normalized


def _detect_bulk_scope_targets(
    extractions: list[dict], classifications: list[dict]
) -> dict[str, dict[str, str]]:
    """LLM의 구조화 결과를 바탕으로 bulk selector 후보를 계산한다."""
    bulk_targets: dict[str, dict[str, str]] = {}
    has_structured_update_intent = any(
        str(ext.get("action") or "").upper() == "UPDATE"
        and (ext.get("property") is not None or ext.get("value") is not None)
        for ext in extractions
    )

    if not has_structured_update_intent:
        return bulk_targets

    categories_with_real_names = {
        _normalize_target_category(str(cls.get("category") or ""))
        for cls in classifications
        if not cls.get("is_category_label")
    }

    for cls in classifications:
        category = _normalize_target_category(str(cls.get("category") or ""))

        if category not in SUPPORTED_BULK_TARGETS:
            continue
        if not cls.get("is_category_label"):
            continue
        if category in categories_with_real_names:
            continue

        cls["bulk_scope"] = "all"
        bulk_targets[category] = {
            "mode": "all",
            "target_file": SUPPORTED_BULK_TARGETS[category]["target_file"],
        }

    return bulk_targets


def _detect_unsupported_bulk_targets(
    extractions: list[dict], classifications: list[dict]
) -> set[str]:
    """구조화 결과상 bulk로 보이지만 현재 미지원인 카테고리를 식별한다."""
    has_structured_update_intent = any(
        str(ext.get("action") or "").upper() == "UPDATE"
        and (ext.get("property") is not None or ext.get("value") is not None)
        for ext in extractions
    )
    if not has_structured_update_intent:
        return set()

    categories_with_real_names = {
        _normalize_target_category(str(cls.get("category") or ""))
        for cls in classifications
        if not cls.get("is_category_label")
    }

    unsupported: set[str] = set()
    for cls in classifications:
        category = _normalize_target_category(str(cls.get("category") or ""))
        if category not in UNSUPPORTED_BULK_TARGETS:
            continue
        if not cls.get("is_category_label"):
            continue
        if category in categories_with_real_names:
            continue
        unsupported.add(category)

    return unsupported


def _build_extracted_ids(classifications: list[dict]) -> dict[str, Any]:
    """분류 단계에서 확정된 ID를 state 전이용 요약 딕셔너리로 구성한다."""
    extracted_ids: dict[str, Any] = {}
    for cls in classifications:
        mapped_id = cls.get("mapped_id")
        if not mapped_id or mapped_id == "NEW":
            continue

        if cls.get("system_ref"):
            extracted_ids[cls["system_ref"]] = mapped_id

        if cls["name"] not in extracted_ids:
            extracted_ids[cls["name"]] = mapped_id

    return extracted_ids


def _has_valid_bulk_selector(
    modifications: list[dict], target: str, required_action: str | None = None
) -> bool:
    """selector.mode=all 형태의 유효한 bulk modification이 있는지 확인한다."""
    normalized_target = _normalize_target_category(target)

    for mod in modifications:
        mod_target = _normalize_target_category(str(mod.get("target") or ""))
        mod_type = str(mod.get("type") or "").lower()
        if mod_target != normalized_target:
            continue
        if required_action and mod_type != required_action:
            continue

        params = mod.get("params", {}) or {}
        selector = params.get("selector")
        if not (isinstance(selector, dict) and selector.get("mode") == "all"):
            continue

        if mod_type == "update":
            updates = params.get("updates")
            if not isinstance(updates, dict) or not updates:
                continue

        return True

    return False


def _has_conflicting_bulk_create(
    modifications: list[dict], bulk_scope_targets: dict[str, dict[str, str]]
) -> bool:
    """지원되는 bulk 대상 요청이 create로 잘못 변환되었는지 확인한다."""
    if not bulk_scope_targets:
        return False

    bulk_targets = set(bulk_scope_targets.keys())
    for mod in modifications:
        if str(mod.get("type") or "").lower() != "create":
            continue
        if _normalize_target_category(str(mod.get("target") or "")) in bulk_targets:
            return True
    return False


def _get_missing_bulk_targets(
    modifications: list[dict], bulk_scope_targets: dict[str, dict[str, str]]
) -> list[str]:
    """지원되는 bulk 대상 중 selector 기반 update가 빠진 카테고리를 계산한다."""
    missing: list[str] = []
    for target in bulk_scope_targets:
        if not _has_valid_bulk_selector(modifications, target, required_action="update"):
            missing.append(target)
    return missing


async def _build_bulk_scope_context(
    retriever: RPGRetriever, game_id: str, bulk_scope_targets: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """bulk 대상에 대한 RAG 기반 요약 컨텍스트를 만든다."""
    context: dict[str, Any] = {}

    for target, config in bulk_scope_targets.items():
        rag_category = SUPPORTED_BULK_TARGETS.get(target, {}).get("rag_category")
        target_file = config["target_file"]

        if rag_category:
            await retriever.index_category(rag_category)
            total_count = vector_store.count(
                retriever.collection_name, where={"category": rag_category, "game_id": game_id}
            )
            sample_limit = min(total_count, 25)
            rows = vector_store.search_by_metadata(
                retriever.collection_name,
                where={"category": rag_category, "game_id": game_id},
                limit=sample_limit,
            )
            context[target] = {
                "scope": "all",
                "target_file": target_file,
                "total_count": total_count,
                "sample_entities": [
                    {
                        "id": row.get("metadata", {}).get("id"),
                        "name": row.get("metadata", {}).get("name"),
                    }
                    for row in rows
                ],
            }
            continue

        if target == "element":
            sys_info = get_system_context(game_id)
            elements = [
                {"id": idx, "name": name}
                for idx, name in enumerate(sys_info.get("elements", []))
                if name
            ]
            context[target] = {
                "scope": "all",
                "target_file": target_file,
                "total_count": len(elements),
                "sample_entities": elements[:25],
            }

    return context


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

        # 4. selector 기반 bulk update/read는 ID 보정 없이 그대로 보존
        raw_params = mod.get("params", {})
        selector = raw_params.get("selector")
        if isinstance(selector, dict) and selector.get("mode"):
            clean_params = dict(raw_params)
            formatted_mods.append({"type": action_type, "target": target, "params": clean_params})
            continue

        # 5. 파라미터 정제 (기존 ID 필드들을 대소문자 구분 없이 찾아서 추출)
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

        # 6. ID 값 확정
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
    messages_2 = build_step2_prompt(extractions, user_input=user_input)
    response_2 = cast(
        Step2ClassificationResponse,
        await invoke_llm(messages=messages_2, structured_output=Step2ClassificationResponse),
    )
    classifications = [cls.model_dump() for cls in response_2.classifications]
    logger.debug("[Definition] Step 2 완료 - 분류된 엔티티 수: %d", len(classifications))
    bulk_scope_targets = _detect_bulk_scope_targets(extractions, classifications)
    unsupported_bulk_targets = _detect_unsupported_bulk_targets(extractions, classifications)
    if bulk_scope_targets:
        logger.info("[Definition] bulk 범위 감지: %s", bulk_scope_targets)
    if unsupported_bulk_targets:
        logger.info("[Definition] 미지원 bulk 범위 감지: %s", sorted(unsupported_bulk_targets))

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
    bulk_context = await _build_bulk_scope_context(retriever, game_id, bulk_scope_targets)
    if bulk_context:
        logger.info("[Definition] bulk RAG 컨텍스트 확보: %s", bulk_context)
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
    final_classifications = filter_category_labels(classifications)

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
        state,
        extractions,
        final_classifications,
        sys_info,
        schema1_content,
        schema2_content,
        bulk_context=bulk_context,
    )

    final_response = cast(
        FinalDefinitionResponse,
        await invoke_llm(messages=messages_5, structured_output=FinalDefinitionResponse),
    )
    logger.debug("[Definition] Step 5 완료 - 대상 파일: %s", final_response.target_files)
    resolved_target_files = list(final_response.target_files)
    resolved_modifications = list(final_response.modifications)
    resolved_params_sufficient = final_response.params_sufficient
    resolved_message_for_user = final_response.message_for_user

    should_retry_bulk_step5 = False
    retry_reason_parts: list[str] = []
    if bulk_scope_targets:
        initial_missing_bulk_targets = _get_missing_bulk_targets(
            resolved_modifications, bulk_scope_targets
        )
        if initial_missing_bulk_targets:
            should_retry_bulk_step5 = True
            retry_reason_parts.append(
                "selector 기반 bulk update가 빠진 대상: " + ", ".join(initial_missing_bulk_targets)
            )
        if _has_conflicting_bulk_create(resolved_modifications, bulk_scope_targets):
            should_retry_bulk_step5 = True
            retry_reason_parts.append("bulk update 요청이 create 작업으로 잘못 변환됨")
        if not resolved_params_sufficient:
            should_retry_bulk_step5 = True
            retry_reason_parts.append("bulk 요청인데 params_sufficient=false로 응답됨")

    if should_retry_bulk_step5:
        logger.warning("[Definition] Step 5 bulk 재시도: %s", " / ".join(retry_reason_parts))
        retry_messages_5 = build_step5_prompt(
            state,
            extractions,
            final_classifications,
            sys_info,
            schema1_content,
            schema2_content,
            bulk_context=bulk_context,
            previous_response=final_response.model_dump(),
            extra_instructions=(
                "- 이전 응답이 bulk contract를 어겼습니다. 이전 응답을 그대로 반복하지 말고 다시 작성하십시오.\n"
                '- bulk update는 반드시 `type="update"` + `params.selector.mode="all"` + `params.updates` 형태여야 합니다.\n'
                "- bulk_context의 total_count가 0이어도 `create`나 추가 정보 질문으로 바꾸지 말고 그대로 bulk update를 반환하십시오.\n"
                "- 지원되는 bulk 대상(actor/enemy/item/weapon/armor/class/state/element)은 빈 집합이어도 params_sufficient=true 여야 합니다."
            ),
        )
        retried_response = cast(
            FinalDefinitionResponse,
            await invoke_llm(messages=retry_messages_5, structured_output=FinalDefinitionResponse),
        )
        resolved_target_files = list(retried_response.target_files)
        resolved_modifications = list(retried_response.modifications)
        resolved_params_sufficient = retried_response.params_sufficient
        resolved_message_for_user = retried_response.message_for_user
        logger.debug("[Definition] Step 5 bulk 재시도 완료 - 대상 파일: %s", resolved_target_files)

    missing_supported_bulk_targets: list[str] = []
    for target, config in bulk_scope_targets.items():
        if _has_valid_bulk_selector(resolved_modifications, target, required_action="update"):
            resolved_target_files = sorted({*(resolved_target_files or []), config["target_file"]})
            continue
        if resolved_params_sufficient:
            missing_supported_bulk_targets.append(target)

    if missing_supported_bulk_targets:
        logger.warning(
            "[Definition] bulk 요청인데 selector 기반 응답이 없어 불충분 처리합니다: %s",
            missing_supported_bulk_targets,
        )
        resolved_params_sufficient = False
        if not resolved_message_for_user:
            targets_str = ", ".join(missing_supported_bulk_targets)
            resolved_message_for_user = f"전체 대상 수정으로 해석됐지만 selector 기반 작업으로 정리되지 않았습니다: {targets_str}"

    if unsupported_bulk_targets and resolved_params_sufficient:
        logger.warning(
            "[Definition] 미지원 bulk 대상이 포함되어 불충분 처리합니다: %s",
            sorted(unsupported_bulk_targets),
        )
        resolved_params_sufficient = False
        if not resolved_message_for_user:
            targets_str = ", ".join(sorted(unsupported_bulk_targets))
            resolved_message_for_user = (
                f"현재 전체 대상 bulk 수정은 {targets_str} 카테고리를 지원하지 않습니다."
            )

    final_extracted_ids = _build_extracted_ids(classifications)

    if not resolved_params_sufficient:
        logger.info("[Definition] params_sufficient=False - 규격 보정/신규 ID 할당을 중단합니다.")
        result = {
            "target_files": resolved_target_files,
            "modifications": resolved_modifications,
            "extracted_ids": final_extracted_ids,
            "params_sufficient": False,
            "message_for_user": resolved_message_for_user,
        }
        logger.info(
            "─── ⚠️ Definition END (elapsed=%.2fs, targets=%d, mods=%d, ids=%d, params_ok=%s) ──",
            time.perf_counter() - _t0,
            len(resolved_target_files),
            len(resolved_modifications),
            len(final_extracted_ids),
            resolved_params_sufficient,
        )
        return result

    # --- [규격 강제 보정 로직 호출] ---
    logger.info("[Definition] Step 6: 규격 준수 여부 확인 및 보정 중...")
    strictly_formatted_mods = _format_to_progress_spec(resolved_modifications, classifications)

    # --- [7단계: 신규 ID 실제 할당 (NEW -> Last ID + 1)] ---
    logger.info("[Definition] Step 7: 신규 생성 대상 ID 할당 중...")
    next_id_cache = {}

    for mod in strictly_formatted_mods:
        target = mod["target"]
        id_field = CATEGORY_TO_ID_FIELD.get(target, f"{target}_id")
        action_type = mod.get("type")
        params = mod.get("params", {})

        if isinstance(params.get("selector"), dict):
            continue

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

    # operation IR 변환 (planner_v2 가 소비)
    operation_tuples = _to_operation_ir(
        strictly_formatted_mods, final_extracted_ids
    )
    logger.info("[Definition] operation IR 변환 완료: %d tuples", len(operation_tuples))

    # 최종 결과 반환
    result = {
        "target_files": resolved_target_files,
        "modifications": strictly_formatted_mods,
        "extracted_ids": final_extracted_ids,
        "params_sufficient": resolved_params_sufficient,
        "message_for_user": resolved_message_for_user,
        "operation_tuples": operation_tuples,
    }
    logger.info(
        "─── ✅ Definition END (elapsed=%.2fs, targets=%d, mods=%d, ids=%d, params_ok=%s) ──",
        time.perf_counter() - _t0,
        len(resolved_target_files),
        len(strictly_formatted_mods),
        len(final_extracted_ids),
        resolved_params_sufficient,
    )
    return result


# ──────────────────────────────────────────────
# Operation IR 변환 — modifications → operation_tuples
# planner_v2 가 소비하는 정규화된 IR 형식
# ──────────────────────────────────────────────

# target(category) → file 매핑
_TARGET_TO_FILE: dict[str, str] = {
    "actor": "Actors.json",
    "enemy": "Enemies.json",
    "item": "Items.json",
    "skill": "Skills.json",
    "weapon": "Weapons.json",
    "armor": "Armors.json",
    "class": "Classes.json",
    "state": "States.json",
    "element": "System.json",
    "system": "System.json",
}

# 배열 필드와 그에 어울리는 array_op match_hint 추론
_ARRAY_FIELDS = frozenset({
    "traits", "effects", "actions", "dropItems", "learnings", "equips",
})

# trait code → 의미 매핑 (intake match_hint 와 동일)
_TRAIT_CODE_TO_HINT: dict[int, str] = {
    11: "속성 내성",
    13: "상태 내성",
    21: "능력치 보정",
    22: "추가 능력치",
    31: "공격 속성",
    32: "공격 상태",
    41: "스킬 유형 추가",
    42: "스킬 유형 봉인",
    43: "스킬 추가",
    44: "스킬 봉인",
    51: "무기 유형 장비",
    52: "방어구 유형 장비",
}


def _to_operation_ir(
    modifications: list[dict],
    extracted_ids: dict,
) -> list[dict]:
    """기존 modifications 를 operation_tuples (operation IR) 로 변환.

    modification 형식 (참고):
        {
            "type": "create" | "update" | "delete" | "query",
            "target": "actor" | "enemy" | ...,
            "params": {
                # create: {"name": ..., "description": ..., ...}
                # update: {"selector": {...}, "updates": {...}}
                # query: {"searchTerm": ...}
            }
        }

    operation IR 형식:
        {
            "op": "create" | "update" | "delete" | "read",
            "file": "Actors.json",
            "subject": {"name": str|None, "id": int|None, "scope": "single"|"all"},
            "field": str|None,
            "value": {kind, ref, new_value, type_hint, array_op, match_hint} | None,
        }
    """
    op_type_map = {
        "create": "create",
        "update": "update",
        "delete": "delete",
        "query": "read",
        "read": "read",
    }

    result: list[dict] = []
    for mod in modifications:
        mod_type = (mod.get("type") or "").lower()
        target = (mod.get("target") or "").lower()
        params = mod.get("params") or {}

        op = op_type_map.get(mod_type)
        file = _TARGET_TO_FILE.get(target)
        if not op or not file:
            continue

        if op == "create":
            tuples = _create_to_ir(file, target, params, extracted_ids)
        elif op == "update":
            tuples = _update_to_ir(file, target, params, extracted_ids)
        elif op == "delete":
            tuples = _delete_to_ir(file, target, params, extracted_ids)
        elif op == "read":
            tuples = _read_to_ir(file, target, params)
        else:
            tuples = []

        result.extend(tuples)

    return result


def _create_to_ir(
    file: str, target: str, params: dict, extracted_ids: dict,
) -> list[dict]:
    """create modification → operation IR.

    profiler 가 세부 필드를 채우므로, IR 은 name 만 담는다.
    """
    name = params.get("name") or params.get(f"{target}_name") or ""
    return [{
        "op": "create",
        "file": file,
        "subject": {"name": name, "id": None, "scope": "single"} if name else None,
        "field": None,
        "value": None,
    }]


def _update_to_ir(
    file: str, target: str, params: dict, extracted_ids: dict,
) -> list[dict]:
    """update modification → operation IR.

    updates 전체를 1개 operation 으로 변환한다.
    필드별 분해는 planner_v2 가 처리.
    """
    selector = params.get("selector") or {}
    updates = params.get("updates") or {}

    # selector 분해
    if isinstance(selector, dict):
        scope = "all" if selector.get("mode") == "all" else "single"
        sub_name = selector.get("name")
        sub_id = selector.get("id")
    else:
        scope = "single"
        sub_name = params.get("name")
        sub_id = None

    # extracted_ids 에서 id 보완
    if sub_id is None and sub_name:
        sub_id = extracted_ids.get(sub_name)

    subject = None
    if scope == "all":
        subject = {"name": None, "id": None, "scope": "all"}
    elif sub_name or sub_id:
        subject = {"name": sub_name, "id": sub_id, "scope": "single"}

    if not updates or not isinstance(updates, dict):
        return []

    # updates 전체를 1개 operation 으로. 필드 분해하지 않음.
    return [{
        "op": "update",
        "file": file,
        "subject": subject,
        "field": None,
        "value": {
            "kind": "updates",
            "ref": None,
            "new_value": None,
            "type_hint": None,
            "array_op": None,
            "match_hint": None,
            "raw_updates": updates,
        },
    }]


def _delete_to_ir(
    file: str, target: str, params: dict, extracted_ids: dict,
) -> list[dict]:
    selector = params.get("selector") or {}
    if isinstance(selector, dict):
        sub_name = selector.get("name") or params.get("name")
        sub_id = selector.get("id")
    else:
        sub_name = params.get("name")
        sub_id = None
    if sub_id is None and sub_name:
        sub_id = extracted_ids.get(sub_name)

    return [{
        "op": "delete",
        "file": file,
        "subject": {"name": sub_name, "id": sub_id, "scope": "single"},
        "field": None,
        "value": None,
    }]


def _read_to_ir(file: str, target: str, params: dict) -> list[dict]:
    name = params.get("searchTerm") or params.get("name")
    return [{
        "op": "read",
        "file": file,
        "subject": {"name": name, "id": None, "scope": "single"} if name else None,
        "field": None,
        "value": None,
    }]


def _build_ir_value(field: str, value, target: str) -> dict:
    """field/value → operation IR value 구조.

    배열 필드는 array_op 으로, 일반 필드는 new_value 로.
    """
    # 배열 필드 — 통째 교체 케이스만 처리 (세밀한 array_op 은 planner 가 추론)
    if field in _ARRAY_FIELDS:
        if isinstance(value, list):
            # 통째 교체 — value 전체를 raw 로 전달, planner 가 처리
            return {
                "kind": "array",
                "ref": None,
                "new_value": None,
                "type_hint": None,
                "array_op": "replace",
                "match_hint": None,
                "raw_array": value,
            }
        # 단일 값이 들어온 경우 → 추가
        return {
            "kind": "array",
            "ref": str(value) if value else None,
            "new_value": None,
            "type_hint": None,
            "array_op": "add",
            "match_hint": None,
        }

    # 참조 필드 — equips 등은 위에서 처리됨. classId 등은 ref 필요
    if field == "classId":
        return {
            "kind": "class",
            "ref": str(value) if value else None,
            "new_value": value if isinstance(value, int) else None,
            "type_hint": None,
            "array_op": None,
            "match_hint": None,
        }

    # 일반 필드 — new_value 로
    return {
        "kind": "param",
        "ref": None,
        "new_value": value,
        "type_hint": None,
        "array_op": None,
        "match_hint": None,
    }
