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

# --- 공통 매핑 상수 (agent.constants 에서 가져옴) ---
from agent.constants import (
    ARRAY_FIELDS,
    CATEGORY_TO_FILE,
    CATEGORY_TO_ID_FIELD,
    CATEGORY_TO_PLURAL,
    PROPERTY_TO_FIELD,
    TRAIT_CODE_TO_HINT,
)

# 복수형(파일명/폴더명) -> 단수형(내부 타겟명) 변환용
PLURAL_TO_SINGULAR = {v.lower(): k for k, v in CATEGORY_TO_PLURAL.items()}
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

    # --- [4단계: 구체적 ID 매핑 (GameIndex 기반)] ---
    logger.info("[Definition] Step 4: 엔티티 ID 매핑 중...")
    from difflib import SequenceMatcher

    if not sys_info:
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

        # [일반 케이스: GameIndex 기반 검색 — RAG 대체]
        from agent.game_index import find_entity as gi_find
        target_file = CATEGORY_TO_FILE.get(cls["category"].lower(), "")
        gi_results = gi_find(game_id, cls["name"])
        # target_file 에 맞는 결과만 필터
        if target_file:
            gi_results = [e for e in gi_results if e.file == target_file]

        is_create = any(
            ext["action"] == "CREATE"
            and (ext["subject"] == cls["name"] or ext["value"] == cls["name"])
            for ext in extractions
        )

        if gi_results:
            best = gi_results[0]
            similarity = SequenceMatcher(None, cls["name"].lower(), best.name.lower()).ratio()

            if is_create:
                if similarity >= 0.9:
                    cls["mapped_id"] = best.id
                    cls["actual_name"] = best.name
                    cls["reason"] += f" (중복 이름 발견: {best.name} ID:{best.id})"
                    logger.debug("[Definition] Step 4 중복 이름 발견: %s -> ID:%s", cls["name"], best.id)
                else:
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += f" (새로운 이름으로 판단: {best.name}와 유사도 {similarity:.2f}로 낮음)"
                    logger.debug("[Definition] Step 4 신규 생성(낮은 유사도): %s (vs %s: %.2f)", cls["name"], best.name, similarity)
            else:
                if similarity >= 0.5:
                    cls["mapped_id"] = best.id
                    cls["actual_name"] = best.name
                    cls["reason"] += f" (매칭 성공: {best.name} ID:{best.id})"
                    logger.debug("[Definition] Step 4 매칭 성공: %s -> ID:%s (유사도 %.2f)", cls["name"], best.id, similarity)
                else:
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += f" (데이터를 찾을 수 없어 신규 생성으로 전환: {best.name}와 유사도 {similarity:.2f}로 낮음)"
                    logger.debug("[Definition] Step 4 매칭 실패(신규 전환): %s (vs %s: %.2f)", cls["name"], best.name, similarity)
        else:
            cls["mapped_id"] = "NEW"
            cls["reason"] += " (GameIndex 에서 미발견 → 신규 생성)"
            logger.debug("[Definition] Step 4 GameIndex 미발견(신규): %s", cls["name"])

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

    # --- [4.5단계: 중복 및 지칭어 필터링 + ID 빌드] ---
    final_classifications = filter_category_labels(classifications)
    final_extracted_ids = _build_extracted_ids(classifications)

    # --- [4.6단계: 코드 기반 operation IR 직접 생성 시도] ---
    # Step 1~4 결과만으로 operation_tuples 를 만들 수 있으면 Step 5 LLM 호출을 건너뜀.
    direct_ops = _extractions_to_operation_tuples(
        extractions, final_classifications, final_extracted_ids, game_id,
    )
    if direct_ops:
        logger.info(
            "[Definition] Step 4.6: 코드 기반 IR 생성 성공 (%d ops) → Step 5 건너뜀",
            len(direct_ops),
        )
        # target_files 도 operation 에서 추출
        target_files_from_ops = sorted({op["file"] for op in direct_ops if op.get("file")})
        result = {
            "target_files": target_files_from_ops,
            "modifications": [],  # 기존 형식 비움 (planner_v2 가 operation_tuples 사용)
            "extracted_ids": final_extracted_ids,
            "params_sufficient": True,
            "operation_tuples": direct_ops,
        }
        logger.info(
            "─── ✅ Definition END (elapsed=%.2fs, direct_ops=%d) ──",
            time.perf_counter() - _t0, len(direct_ops),
        )
        return result

    logger.info("[Definition] Step 4.6: 코드 기반 IR 생성 실패 → Step 5 LLM 경로")

    # --- [5단계: 최종 조립 (Specification)] --- (fallback)
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

    # RAG bulk_context — Step 5 fallback 시에만 필요. 지연 초기화.
    bulk_context = {}
    if bulk_scope_targets:
        try:
            retriever = RPGRetriever(game_id)
            bulk_context = await _build_bulk_scope_context(retriever, game_id, bulk_scope_targets)
            if bulk_context:
                logger.info("[Definition] Step 5 bulk RAG 컨텍스트 확보: %s", bulk_context)
        except Exception as e:
            logger.warning("[Definition] bulk RAG 컨텍스트 실패 (무시): %s", e)

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

    # final_extracted_ids 는 Step 4.5 에서 이미 생성됨 (Step 4.6 에서 사용)

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

# _TARGET_TO_FILE, ARRAY_FIELDS, TRAIT_CODE_TO_HINT, CATEGORY_TO_FILE
# → agent.constants 의 CATEGORY_TO_FILE, ARRAY_FIELDS, TRAIT_CODE_TO_HINT 로 통합
# System.json 전용 확장
_TARGET_TO_FILE: dict[str, str] = {**CATEGORY_TO_FILE, "element": "System.json", "system": "System.json"}


# ──────────────────────────────────────────────
# Step 4.6: 코드 기반 operation IR 직접 생성
# Step 1~4 결과(extractions + classifications)에서 LLM 없이 operation_tuples 생성
# ──────────────────────────────────────────────

# extraction.property → (field, value.kind) 매핑
# property 가 이 테이블에 있으면 코드 기반 변환 가능
# PROPERTY_TO_FIELD 는 agent.constants 에서 import


def _extractions_to_operation_tuples(
    extractions: list[dict],
    classifications: list[dict],
    extracted_ids: dict,
    game_id: str,
) -> list[dict]:
    """Step 1~4 결과에서 직접 operation_tuples 를 생성한다.

    모든 extraction 을 변환할 수 없으면 빈 리스트를 반환 (fallback 신호).

    Returns:
        list[dict] — 성공 시 operation_tuples, 실패 시 [].
    """
    # classification 을 이름 기반 lookup 으로 구성
    cls_by_name: dict[str, dict] = {}
    for cls in classifications:
        name = cls.get("name", "").strip()
        if name:
            cls_by_name[name.lower()] = cls

    logger.debug(
        "[Step4.6] cls_by_name keys=%s, extractions=%d",
        list(cls_by_name.keys()), len(extractions),
    )

    ops: list[dict] = []

    for ext in extractions:
        action = (ext.get("action") or "").upper().strip()
        subject = (ext.get("subject") or "").strip()
        prop = (ext.get("property") or "").strip()
        value_str = (ext.get("value") or "").strip()

        if not subject:
            return []  # 변환 불가

        # subject 의 분류 정보 찾기 — 완전 일치 → 부분 포함
        sub_cls = cls_by_name.get(subject.lower())
        if not sub_cls:
            # 부분 일치 fallback (예: subject="리드" vs cls name="리드 액터")
            for cname, cval in cls_by_name.items():
                if subject.lower() in cname or cname in subject.lower():
                    sub_cls = cval
                    break
        if not sub_cls:
            # System.json 수정: subject 가 카테고리 지칭어("게임", "시스템" 등)로 필터된 경우
            if prop and value_str and action == "UPDATE":
                sys_field = _detect_system_field(subject, prop)
                if sys_field:
                    logger.info("[Step4.6] System.json 수정 감지: %s.%s = %s", subject, sys_field, value_str)
                    ops.append({
                        "op": "update",
                        "file": "System.json",
                        "subject": None,
                        "field": sys_field,
                        "value": {"kind": "string", "ref": None, "new_value": value_str, "type_hint": None, "array_op": None, "match_hint": None},
                    })
                    continue
            logger.info("[Step4.6] subject '%s' not in cls_by_name %s → fallback", subject, list(cls_by_name.keys()))
            return []

        sub_cat = (sub_cls.get("category") or "").lower()
        sub_id = sub_cls.get("mapped_id")
        if isinstance(sub_id, str):
            sub_id = None if sub_id == "NEW" else int(sub_id) if sub_id.isdigit() else None

        # extracted_ids 에서도 보완
        if sub_id is None:
            sub_id = extracted_ids.get(subject)

        sub_file = CATEGORY_TO_FILE.get(sub_cat)
        if not sub_file and sub_cat not in ("element", "system", "none"):
            return []

        # CREATE
        if action == "CREATE":
            ops.append({
                "op": "create",
                "file": sub_file or "System.json",
                "subject": {"name": subject, "id": None, "scope": "single"},
                "field": None,
                "value": None,
            })
            continue

        # DELETE
        if action == "DELETE":
            ops.append({
                "op": "delete",
                "file": sub_file or "System.json",
                "subject": {"name": subject, "id": sub_id, "scope": "single"},
                "field": None,
                "value": None,
            })
            continue

        # READ
        if action == "READ":
            ops.append({
                "op": "read",
                "file": sub_file or "System.json",
                "subject": {"name": subject, "id": sub_id, "scope": "single"},
                "field": prop if prop else None,
                "value": None,
            })
            continue

        # UPDATE — property 로 field 결정
        if action == "UPDATE":
            if not prop and not value_str:
                return []  # 뭘 수정하는지 모름

            # value 에 대한 분류 정보 (참조 엔티티일 수 있음) — 완전 → 부분 일치
            val_cls = None
            if value_str:
                val_cls = cls_by_name.get(value_str.lower())
                if not val_cls:
                    for cname, cval in cls_by_name.items():
                        if value_str.lower() in cname or cname in value_str.lower():
                            val_cls = cval
                            break

            # property 가 없으면 value 의 카테고리로 추론
            if not prop and val_cls:
                val_cat = (val_cls.get("category") or "").lower()
                prop = _infer_property_from_value_category(val_cat)

            if not prop:
                return []  # field 결정 불가

            # property → field 매핑
            field_info = _lookup_property_field(prop)
            if not field_info:
                return []

            field, kind = field_info

            # value 구성
            ir_value = _build_direct_ir_value(
                field, kind, value_str, val_cls, extracted_ids, prop=prop,
            )

            ops.append({
                "op": "update",
                "file": sub_file,
                "subject": {"name": subject, "id": sub_id, "scope": "single"},
                "field": field,
                "value": ir_value,
            })
            continue

        # 알 수 없는 action
        return []

    return ops


def _lookup_property_field(prop: str) -> tuple[str, str] | None:
    """property 문자열에서 field 매핑을 찾는다. 완전 일치 → 부분 일치."""
    t = prop.lower().replace(" ", "")
    # 완전 일치
    for key, val in PROPERTY_TO_FIELD.items():
        if key.replace(" ", "") == t:
            return val
    # 부분 포함
    for key, val in PROPERTY_TO_FIELD.items():
        if key in prop or prop in key:
            return val
    return None


def _detect_system_field(subject: str, prop: str) -> str | None:
    """subject + property 에서 System.json 필드를 감지. 해당하면 필드명 반환."""
    combined = (subject + " " + prop).lower()
    if "제목" in combined or "타이틀" in combined:
        return "gameTitle"
    if "통화" in combined or "화폐" in combined:
        return "currencyUnit"
    return None


def _infer_property_from_value_category(val_cat: str) -> str:
    """value 의 카테고리에서 property 를 추론."""
    return {
        "skill": "스킬",
        "weapon": "무기",
        "armor": "장비",
        "class": "직업",
        "item": "드롭",
        "state": "속성",
        "element": "속성",
    }.get(val_cat, "")


def _build_direct_ir_value(
    field: str,
    kind: str,
    value_str: str,
    val_cls: dict | None,
    extracted_ids: dict,
    prop: str = "",
) -> dict:
    """직접 변환용 IR value 생성."""
    val_id = None
    if val_cls:
        mid = val_cls.get("mapped_id")
        if isinstance(mid, int):
            val_id = mid
        elif isinstance(mid, str) and mid.isdigit():
            val_id = int(mid)
    if val_id is None and value_str:
        val_id = extracted_ids.get(value_str)

    # 참조 필드 (learnings, equips, classId, actions, dropItems)
    if kind in ("skill", "weapon", "armor", "class", "item"):
        return {
            "kind": kind,
            "ref": value_str if value_str else None,
            "new_value": None,
            "type_hint": prop if prop else None,  # "방패", "장신구" 등 슬롯 힌트
            "array_op": None,
            "match_hint": None,
        }

    # trait 관련
    if kind == "trait":
        return {
            "kind": "trait",
            "ref": value_str if value_str else None,
            "new_value": None,
            "type_hint": None,
            "array_op": "update",
            "match_hint": "공격 속성" if "속성" in field or "공격" in (value_str or "") else None,
        }

    # 단순 값 (string, param)
    if kind == "param":
        try:
            num = int(value_str) if value_str else None
        except ValueError:
            try:
                num = float(value_str)
            except ValueError:
                num = None
        return {
            "kind": "param",
            "ref": None,
            "new_value": num,
            "type_hint": None,
            "array_op": None,
            "match_hint": None,
        }

    # string
    return {
        "kind": "string",
        "ref": None,
        "new_value": value_str if value_str else None,
        "type_hint": None,
        "array_op": None,
        "match_hint": None,
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

    세부 필드 값(params, traits, effects 등)은 profiler 책임이므로 여기서는
    스칼라 필드(name, initialLevel 등)만 raw_updates 로 전달한다.
    배열/복합 필드는 field 이름만 남기고 값은 버린다.
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

    # profiler 가 채울 복합 필드(traits, effects, params 등)는 버리고,
    # 스칼라 + 참조 필드(equips, classId 등)는 남긴다.
    _PROFILER_FIELDS = {"traits", "effects", "damage", "params", "actions", "dropItems", "learnings"}
    filtered_updates = {k: v for k, v in updates.items() if k not in _PROFILER_FIELDS}

    if not filtered_updates:
        return []

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
            "raw_updates": filtered_updates,
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


# _build_ir_value 삭제 — _update_to_ir 에서 스칼라만 통과시키므로 불필요.
