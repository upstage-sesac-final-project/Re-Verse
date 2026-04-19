"""Definition 노드 — 1단계: 핵심 키워드 추출."""

import logging
import os
import time
from typing import Any, cast

from agent.constants import (
    CATEGORY_TO_FILE,
    CATEGORY_TO_ID_FIELD,
    CATEGORY_TO_PLURAL,
)
from agent.core.llm_client import invoke_llm
from agent.editor.operation_ir import (
    apply_index_resolution,
    build_from_extractions,
    normalize_modifications,
    validate_operation_tuples,
)
from agent.editor.prompts.definition_prompt import (
    build_step1_prompt,
    build_step2_prompt,
    build_step5_prompt,
)
from agent.editor.schemas import (
    FinalDefinitionResponse,
    Step1ExtractionResponse,
    Step2ClassificationResponse,
)
from agent.editor.state import AgentState
from agent.rag.retriever import RPGRetriever
from agent.rag.vectorstore import vector_store
from agent.utils.game_data_io import get_next_entity_id, get_system_context

logger = logging.getLogger(__name__)

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
    4. 지칭어 제거 시, 같은 카테고리가 아닌 구체 entity 중 create 대상(id=NEW)이
       있으면 지칭어의 카테고리로 덮어쓴다.
       예: "방어구에 치유의 목걸이 만들어줘" → '방어구' 제거 + '치유의 목걸이'를 Armor로 보정.
    """
    categories_with_real_names = {
        cls["category"] for cls in classifications if not cls.get("is_category_label")
    }
    has_non_label_entity = any(not c.get("is_category_label") for c in classifications)

    # 제거될 지칭어의 카테고리 수집
    label_categories: list[str] = []
    if has_non_label_entity:
        for cls in classifications:
            if cls.get("is_category_label"):
                label_categories.append(cls["category"])

    # 지칭어 카테고리를 create(NEW) 대상에 전파
    if label_categories:
        label_cat = label_categories[0]  # 지칭어가 여러 개면 첫 번째 사용
        for cls in classifications:
            if cls.get("is_category_label"):
                continue
            # 신규 생성 대상이고 지칭어 카테고리와 다르면 보정
            is_new = cls.get("mapped_id") == "NEW" or cls.get("mapped_id") is None
            if is_new and cls["category"] != label_cat:
                logger.info(
                    "[Definition] 지칭어 카테고리 전파: %s의 카테고리 %s → %s",
                    cls["name"],
                    cls["category"],
                    label_cat,
                )
                cls["category"] = label_cat

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


async def _definition_core(state: AgentState) -> dict:
    """사용자 입력을 operation IR 로 변환하는 10 단계 파이프라인.

    Phase D+E-3 에서 Step 1/2/5/5.5/6/7 이 rule-base 로 대체될 예정.
    현재는 기존 Step 구조 유지. 상위 `definition` wrapper 가 hold / pending /
    신규 contract 필드 (field / target / description / reference_checks / resolve) 를 보강한다.

    각 Step 의 역할은 다음과 같습니다:
        Step 1  extract_keywords          LLM 으로 subject/property/value/action 추출.
        Step 2  classify_entities         추출된 subject 들을 Actor/Enemy/Item/... 카테고리로 분류.
        Step 3  resolve_system_refs       "주인공" / "게임 제목" / "화폐" 등 system_ref 를 System.json 기반으로 실체화.
        Step 4  map_entity_ids            GameIndex 로 엔티티 이름 → ID 매핑. 내부에서 중복·지칭어 필터링 + final_extracted_ids 빌드.
        Step 5  direct_ir_synthesis       Step 1~4 결과만으로 operation_tuples 를 코드 기반으로 즉시 생성 (LLM 0 회 이상적 경로).
                                          맵 CREATE 요청 시 현재 쿼리로 샘플맵 재랭킹 수행.
        Step 6  llm_modifications_fallback  Step 5 실패 시 LLM 으로 최종 수정 명세(modifications) 생성.
                                          내부에서 bulk 재시도 1회 가능.
        Step 7  normalize_modifications   Step 6 출력의 규격 준수 여부 확인 및 키/값 보정.
        Step 8  assign_new_ids            신규 생성 대상(NEW) 에 실제 ID 할당.
        Step 9  resolve_index_postproc    GameIndex 기반 operation IR 후처리 (id/file/ref 확정, 장비 type_hint 보정).
        Step 10 validate_degenerate       update/delete/read 인데 대상 미식별 또는 updates 비어 있는 op 차단.

    경로 선택:
        - Step 5 성공 → Step 6~8 건너뛰고 Step 9·10 만 수행하고 반환.
        - Step 5 실패 → Step 6 LLM fallback 경로로 진행.
    """
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

    # Step 1 post-check: subject/value 가 현재 user_input 내부 substring 이어야 함.
    # 이전 대화의 엔티티가 LLM hallucination 으로 넘어온 경우를 차단 (1-② 오염 방지).
    def _norm(s: str) -> str:
        return s.replace(" ", "").lower()

    _ui_norm = _norm(user_input)
    _cleaned: list[dict] = []
    for ext in extractions:
        subj = str(ext.get("subject") or "").strip()
        if subj and _norm(subj) not in _ui_norm:
            logger.warning(
                "[Definition] Step 1 post-check: subject '%s' 가 현재 user_input 에 없음 → 추출 제거 (history 오염 의심)",
                subj,
            )
            continue
        val = ext.get("value")
        if isinstance(val, str) and val.strip():
            # 숫자·기호는 제외하고, 엔티티 이름류 value 만 검사
            val_s = val.strip()
            is_numeric = val_s.replace(".", "", 1).lstrip("-").isdigit()
            if not is_numeric and _norm(val_s) not in _ui_norm:
                logger.warning(
                    "[Definition] Step 1 post-check: value '%s' 가 현재 user_input 에 없음 → value 비움",
                    val_s,
                )
                ext["value"] = None
        _cleaned.append(ext)
    extractions = _cleaned

    # --- [2단계: 카테고리 분류] ---
    logger.info("[Definition] Step 2: 추출된 대상들 카테고리 분류 중...")
    messages_2 = build_step2_prompt(extractions, user_input=user_input)
    response_2 = cast(
        Step2ClassificationResponse,
        await invoke_llm(messages=messages_2, structured_output=Step2ClassificationResponse),
    )
    classifications = [cls.model_dump() for cls in response_2.classifications]
    logger.debug("[Definition] Step 2 완료 - 분류된 엔티티 수: %d", len(classifications))

    # category=None 보정: 한국어 키워드 매핑으로 복구 가능하면 복구, 아니면 제거
    from agent.constants import KEYWORD_TO_CATEGORY

    kept: list[dict] = []
    removed_count = 0
    for cls in classifications:
        if cls.get("category") is not None:
            kept.append(cls)
            continue
        name = (cls.get("name") or "").strip()
        matched_cat = KEYWORD_TO_CATEGORY.get(name)
        if matched_cat:
            cls["category"] = matched_cat
            cls["is_category_label"] = True
            logger.info("[Definition] 키워드 매핑으로 카테고리 복구: %s -> %s", name, matched_cat)
            kept.append(cls)
        else:
            removed_count += 1
    classifications = kept
    if removed_count:
        logger.info("[Definition] category=None 분류 %d건 제거 (수치 표현 등)", removed_count)

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
        from agent.editor.game_index import find_entity as gi_find

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

            # 짧은 이름(2자 이하)은 fuzzy 오매칭 위험이 커 exact 만 허용
            short_name = len(cls["name"].strip()) <= 2
            if short_name and cls["name"].lower() != best.name.lower():
                cls["mapped_id"] = "NEW"
                cls["reason"] += (
                    f" (짧은 이름 guard: '{cls['name']}' 은 exact 매칭 외 fuzzy 차단, "
                    f"best='{best.name}' 유사도 {similarity:.2f})"
                )
                logger.debug(
                    "[Definition] Step 4 짧은 이름 guard: %s vs %s (%.2f) → NEW",
                    cls["name"],
                    best.name,
                    similarity,
                )
                continue

            if is_create:
                if similarity >= 0.9:
                    cls["mapped_id"] = best.id
                    cls["actual_name"] = best.name
                    cls["reason"] += f" (중복 이름 발견: {best.name} ID:{best.id})"
                    logger.debug(
                        "[Definition] Step 4 중복 이름 발견: %s -> ID:%s", cls["name"], best.id
                    )
                else:
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += (
                        f" (새로운 이름으로 판단: {best.name}와 유사도 {similarity:.2f}로 낮음)"
                    )
                    logger.debug(
                        "[Definition] Step 4 신규 생성(낮은 유사도): %s (vs %s: %.2f)",
                        cls["name"],
                        best.name,
                        similarity,
                    )
            else:
                if similarity >= 0.5:
                    cls["mapped_id"] = best.id
                    cls["actual_name"] = best.name
                    cls["reason"] += f" (매칭 성공: {best.name} ID:{best.id})"
                    logger.debug(
                        "[Definition] Step 4 매칭 성공: %s -> ID:%s (유사도 %.2f)",
                        cls["name"],
                        best.id,
                        similarity,
                    )
                else:
                    cls["mapped_id"] = "NEW"
                    cls["reason"] += (
                        f" (데이터를 찾을 수 없어 신규 생성으로 전환: {best.name}와 유사도 {similarity:.2f}로 낮음)"
                    )
                    logger.debug(
                        "[Definition] Step 4 매칭 실패(신규 전환): %s (vs %s: %.2f)",
                        cls["name"],
                        best.name,
                        similarity,
                    )
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

    # --- [Step 4 내부: 중복 및 지칭어 필터링 + ID 빌드] ---
    final_classifications = filter_category_labels(classifications)
    final_extracted_ids = _build_extracted_ids(classifications)

    # --- [Step 5: 코드 기반 operation IR 직접 생성 시도] ---
    # Step 1~4 결과만으로 operation_tuples 를 만들 수 있으면 Step 6 LLM 호출을 건너뜀.

    # 맵 CREATE 요청이 있으면 현재 쿼리로 샘플맵 재랭킹 (게임 생성 때 저장된 후보는 다른 쿼리 기반)
    ranked_map_candidates: list[dict] = state.get("ranked_map_candidates") or []
    _map_cat_names: set[str] = {
        (c.get("name") or "").strip().lower()
        for c in final_classifications
        if (c.get("category") or "").lower() == "map"
    }
    _has_map_create = any(
        (e.get("action") or "").upper() == "CREATE"
        and any(
            mname
            and (
                mname in (e.get("subject") or "").lower()
                or (e.get("subject") or "").lower() in mname
            )
            for mname in _map_cat_names
        )
        for e in extractions
    )
    if _has_map_create and user_input:
        try:
            from agent.generation.mapgen.sample_selector import select_maps

            logger.info("[Step5] 맵 추가 요청 감지 → 현재 쿼리로 샘플맵 재랭킹: '%s'", user_input)
            _map_result = await select_maps(user_input, n_maps=1)
            if _map_result.get("candidates"):
                ranked_map_candidates = _map_result["candidates"]
                logger.info(
                    "[Step5] 재랭킹 완료: best=%s (score=%.3f)",
                    ranked_map_candidates[0]["entry"]["file_name"],
                    ranked_map_candidates[0].get("score", 0.0),
                )
            else:
                logger.warning("[Step5] 재랭킹 결과 없음 → 기존 후보 유지")
        except Exception as _e:
            logger.warning("[Step5] 샘플맵 재랭킹 실패: %s → 기존 후보 유지", _e)

    direct_ops = build_from_extractions(
        extractions,
        final_classifications,
        final_extracted_ids,
        game_id,
        ranked_map_candidates=ranked_map_candidates,
        user_input=user_input,
    )
    if direct_ops:
        logger.info(
            "[Definition] Step 5: 코드 기반 IR 생성 성공 (%d ops) → Step 6 건너뜀",
            len(direct_ops),
        )
        # Step 9: GameIndex 기반 operation IR 후처리 (id/file/ref 확정, 장비 type_hint 보정)
        direct_ops = apply_index_resolution(direct_ops, game_id)

        # Step 10: degenerate op 검증 (update/update_all with empty updates → params_sufficient=False)
        ok, reason = validate_operation_tuples(direct_ops, extractions)
        if not ok:
            logger.info("[Definition] Step 5 검증 실패(degenerate): %s", reason)
            return {
                "target_files": [],
                "modifications": [],
                "extracted_ids": final_extracted_ids,
                "params_sufficient": False,
                "message_for_user": reason,
                "final_response": reason,
                "operation_tuples": [],
            }

        # target_files 도 operation 에서 추출
        target_files_from_ops = sorted({op["file"] for op in direct_ops if op.get("file")})
        result = {
            "target_files": target_files_from_ops,
            "modifications": [],  # 기존 형식 비움 (planner 가 operation_tuples 사용)
            "extracted_ids": final_extracted_ids,
            "params_sufficient": True,
            "operation_tuples": direct_ops,
        }
        logger.info(
            "─── ✅ Definition END (elapsed=%.2fs, direct_ops=%d) ──",
            time.perf_counter() - _t0,
            len(direct_ops),
        )
        return result

    logger.info("[Definition] Step 5: 코드 기반 IR 생성 실패 → Step 6 LLM 경로")

    # --- [Step 6: 최종 조립 (Specification)] --- (fallback)
    logger.info("[Definition] Step 6: 최종 수정 명세 생성 중...")

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

    # RAG bulk_context — Step 6 fallback 시에만 필요. 지연 초기화.
    bulk_context = {}
    if bulk_scope_targets:
        try:
            retriever = RPGRetriever(game_id)
            bulk_context = await _build_bulk_scope_context(retriever, game_id, bulk_scope_targets)
            if bulk_context:
                logger.info("[Definition] Step 6 bulk RAG 컨텍스트 확보: %s", bulk_context)
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
    logger.debug("[Definition] Step 6 완료 - 대상 파일: %s", final_response.target_files)
    resolved_target_files = list(final_response.target_files)
    resolved_modifications = list(final_response.modifications)
    resolved_params_sufficient = final_response.params_sufficient
    resolved_message_for_user = final_response.message_for_user

    # Step 6 결정론 post-process: Step 1·2 결과 존중 강제
    # 6-①: params.name 이 user_input 에 없으면 Step 1 subject 로 강제 덮어쓰기 (name hallucination 차단)
    # 6-②: target 카테고리가 classifications 와 어긋나면 classifications 기준으로 교정
    _ui_norm_for_step6 = user_input.replace(" ", "").lower()
    _subjects_by_cat: dict[str, list[str]] = {}
    for _cls in final_classifications:
        _cat = str(_cls.get("category") or "").lower()
        _nm = (_cls.get("name") or "").strip()
        if _cat and _nm and not _cls.get("is_category_label"):
            _subjects_by_cat.setdefault(_cat, []).append(_nm)

    # classifications lookup by normalized name
    _cls_by_norm_name: dict[str, dict] = {}
    for _cls in final_classifications:
        _nm = (_cls.get("name") or "").strip()
        if _nm and not _cls.get("is_category_label"):
            _cls_by_norm_name[_nm.replace(" ", "").lower()] = _cls

    for mod in resolved_modifications:
        params = mod.get("params") or {}
        if not isinstance(params, dict):
            continue
        if isinstance(params.get("selector"), dict):
            continue

        # 6-② / 6-③: target 이 classifications 와 어긋나면 교정 (create 포함)
        name = params.get("name")
        if isinstance(name, str) and name.strip():
            matched_cls = _cls_by_norm_name.get(name.replace(" ", "").lower())
            if matched_cls:
                correct_cat = _normalize_target_category(str(matched_cls.get("category") or ""))
                current_cat = _normalize_target_category(str(mod.get("target") or ""))
                if correct_cat and correct_cat != current_cat:
                    logger.warning(
                        "[Definition] Step 6 post-process: target 재라우팅 '%s' → '%s' (classifications 기준, name='%s')",
                        current_cat,
                        correct_cat,
                        name,
                    )
                    mod["target"] = correct_cat

        # 6-①: name 이 user_input 에 없으면 classifications 의 subject 로 강제 덮어쓰기
        if not isinstance(name, str) or not name.strip():
            continue
        if name.replace(" ", "").lower() in _ui_norm_for_step6:
            continue
        target_cat = _normalize_target_category(str(mod.get("target") or ""))
        candidates = _subjects_by_cat.get(target_cat) or []
        if candidates:
            logger.warning(
                "[Definition] Step 6 post-process: hallucinated name '%s' → '%s' (classifications[%s])",
                name,
                candidates[0],
                target_cat,
            )
            params["name"] = candidates[0]
        else:
            logger.warning(
                "[Definition] Step 6 post-process: hallucinated name '%s' 감지했으나 classifications 에 대체 후보 없음",
                name,
            )

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
        logger.warning("[Definition] Step 6 bulk 재시도: %s", " / ".join(retry_reason_parts))
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
        logger.debug("[Definition] Step 6 bulk 재시도 완료 - 대상 파일: %s", resolved_target_files)

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

    # final_extracted_ids 는 Step 4 내부에서 이미 생성됨 (Step 5 에서 사용)

    if not resolved_params_sufficient:
        logger.info("[Definition] params_sufficient=False - 규격 보정/신규 ID 할당을 중단합니다.")
        # 사용자에게 보여줄 메시지가 없으면 기본 메시지 생성
        if not resolved_message_for_user:
            resolved_message_for_user = (
                "요청을 처리하기 위한 정보가 부족합니다. "
                "구체적인 수치나 대상을 포함해서 다시 말씀해주세요."
            )
        result = {
            "target_files": resolved_target_files,
            "modifications": resolved_modifications,
            "extracted_ids": final_extracted_ids,
            "params_sufficient": False,
            "message_for_user": resolved_message_for_user,
            "final_response": resolved_message_for_user,
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
    logger.info("[Definition] Step 7: 규격 준수 여부 확인 및 보정 중...")
    strictly_formatted_mods = _format_to_progress_spec(resolved_modifications, classifications)

    # --- [7단계: 신규 ID 실제 할당 (NEW -> Last ID + 1)] ---
    logger.info("[Definition] Step 8: 신규 생성 대상 ID 할당 중...")
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

    # operation IR 변환 (planner 가 소비)
    operation_tuples = normalize_modifications(strictly_formatted_mods, final_extracted_ids)
    logger.info("[Definition] operation IR 변환 완료: %d tuples", len(operation_tuples))

    # Step 9: GameIndex 기반 operation IR 후처리 (id/file/ref 확정, 장비 type_hint 보정)
    operation_tuples = apply_index_resolution(operation_tuples, game_id)

    # Step 10: degenerate op 검증 (update/update_all with empty updates → params_sufficient=False)
    degenerate_response: str | None = None
    if resolved_params_sufficient:
        ok, reason = validate_operation_tuples(operation_tuples, extractions)
        if not ok:
            logger.info("[Definition] 검증 실패(degenerate): %s", reason)
            resolved_params_sufficient = False
            resolved_message_for_user = reason
            operation_tuples = []
            degenerate_response = reason

    # 최종 결과 반환
    result = {
        "target_files": resolved_target_files,
        "modifications": strictly_formatted_mods,
        "extracted_ids": final_extracted_ids,
        "params_sufficient": resolved_params_sufficient,
        "message_for_user": resolved_message_for_user,
        "operation_tuples": operation_tuples,
    }
    if degenerate_response is not None:
        result["final_response"] = degenerate_response
    logger.info(
        "─── ✅ Definition END (elapsed=%.2fs, targets=%d, mods=%d, ids=%d, params_ok=%s) ──",
        time.perf_counter() - _t0,
        len(resolved_target_files),
        len(strictly_formatted_mods),
        len(final_extracted_ids),
        resolved_params_sufficient,
    )
    return result


# ═════════════════════════════════════════════════════════════════════════════
# Phase D+E-1 wrapper — hold / pending_store / 신규 contract 필드 보강
# ═════════════════════════════════════════════════════════════════════════════


# 기존 CATEGORY_TO_FILE 의 역매핑: "Weapons.json" → "무기" 같은 한국어 라벨.
_FILE_TO_KOREAN_LABEL = {
    "Actors.json": "액터",
    "Classes.json": "직업",
    "Skills.json": "스킬",
    "Items.json": "아이템",
    "Weapons.json": "무기",
    "Armors.json": "방어구",
    "Enemies.json": "적",
    "Troops.json": "트룹",
    "States.json": "상태이상",
    "Animations.json": "애니메이션",
    "Tilesets.json": "타일셋",
    "CommonEvents.json": "공용이벤트",
    "System.json": "시스템",
    "MapInfos.json": "맵",
}


def _infer_field_label(target_files: list[str], parsed_command: dict | None) -> str:
    """field 라벨 추론. parsed_command.field 우선, 없으면 target_files 첫 번째로부터."""
    if parsed_command:
        f = (parsed_command.get("field") or "").strip()
        if f:
            return f
    for tf in target_files:
        if tf in _FILE_TO_KOREAN_LABEL:
            return _FILE_TO_KOREAN_LABEL[tf]
        if tf.startswith("Map") and tf.endswith(".json"):
            return "이벤트"
    return ""


def _infer_target_label(
    modifications: list[dict], extracted_ids: dict, parsed_command: dict | None
) -> str:
    """target (확정된 대상 요약). parsed_command.target 우선."""
    if parsed_command:
        t = (parsed_command.get("target") or "").strip()
        if t:
            return t
    # modifications[0].params.name 또는 extracted_ids 첫 번째
    for mod in modifications or []:
        params = mod.get("params") if isinstance(mod, dict) else None
        if isinstance(params, dict):
            name = params.get("name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    for k in extracted_ids or {}:
        if isinstance(k, str) and k.strip():
            return k.strip()
    return ""


def _infer_hold_reason(message_for_user: str) -> str:
    """message_for_user 에서 hold_reason 추론 (heuristic).

    Phase D+E-3 에서 rule-base 분기로 정확한 reason 생성 예정.
    현재는 대부분의 clarification 케이스가 'not_found' 혹은 'ambiguous_ref'
    중 하나라서 키워드 기반 분류만 함.
    """
    if not message_for_user:
        return "ambiguous_ref"
    m = message_for_user
    if ("찾을 수 없" in m) or ("없습니다" in m) or ("존재하지 않" in m) or ("미식별" in m):
        return "not_found"
    if ("이미 있" in m) or ("이미 존재" in m):
        return "already_exists"
    return "ambiguous_ref"


async def definition(state: AgentState) -> dict:
    """Phase D+E-1 wrapper.

    책임:
    1. router 의 `resumed_snapshot` 복원 — 이전 턴의 user_input 로 재실행
    2. 본체 `_definition_core` 실행
    3. 결과에 신규 contract 필드 보강: field / target / description / reference_checks / resolve
    4. hold 발생 시 pending_store 에 set (conversation_id 있을 때)

    Phase D+E-3 에서 본체 Step 1/2/5/5.5/6/7 제거 + 재작성 예정.
    """
    from agent.editor.pending_store import get_default_store

    # ── 1. resumed_snapshot 복원 ─────────────────────────────────
    resumed = state.get("resumed_snapshot") or {}
    if resumed and state.get("pending_resumed"):
        # 이전 턴 user_input 이 snapshot 에 있다면 복원.
        # 현재는 snapshot 형태가 고정 안 됐으니 얕은 merge 만.
        restored_keys = [k for k in resumed if k not in state]
        if restored_keys:
            logger.info(
                "[Definition] pending resume: snapshot 복원 키 = %s", restored_keys
            )
            # state 는 TypedDict 지만 dict 로 취급 가능
            for k in restored_keys:
                state[k] = resumed[k]  # type: ignore[literal-required]

    # ── 2. 본체 실행 ─────────────────────────────────────────────
    result = await _definition_core(state)

    # ── 3. 신규 contract 필드 보강 ──────────────────────────────
    parsed_command = state.get("parsed_command") or {}
    target_files = result.get("target_files") or []
    modifications = result.get("modifications") or []
    extracted_ids = result.get("extracted_ids") or {}

    field_label = _infer_field_label(target_files, parsed_command)
    target_label = _infer_target_label(modifications, extracted_ids, parsed_command)
    description = state.get("user_input") or ""

    result["field"] = field_label
    result["target"] = target_label
    result["description"] = description
    # reference_checks 는 D+E-3 에서 rule-base 로 생성. 지금은 비어 있음.
    result.setdefault("reference_checks", [])

    # ── 4. resolve / hold 분기 + pending_store set ───────────────
    params_ok = bool(result.get("params_sufficient", False))
    if not params_ok:
        # hold 상태
        result["resolve"] = False
        msg = result.get("message_for_user") or ""
        hold_reason = _infer_hold_reason(msg)
        result["hold_reason"] = hold_reason
        result["hold_question"] = msg or "추가 정보가 필요합니다."

        # pending_store 에 저장 (conversation_id 있을 때만)
        cid = state.get("conversation_id") or ""
        if cid:
            try:
                snapshot = {
                    "user_input": state.get("user_input", ""),
                    "parsed_command": parsed_command,
                    "field": field_label,
                    "target": target_label,
                    "description": description,
                }
                get_default_store().set(
                    cid,
                    hold_reason=hold_reason,  # type: ignore[arg-type]
                    hold_question=result["hold_question"],
                    snapshot=snapshot,
                )
                logger.info(
                    "[Definition] pending_store.set (cid=%s, reason=%s)", cid, hold_reason
                )
            except Exception as e:  # pragma: no cover — store 장애는 로직 차단 금지
                logger.warning("[Definition] pending_store.set 실패: %s", e)
    else:
        result["resolve"] = True

    return result
