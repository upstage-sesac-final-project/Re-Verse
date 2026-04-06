"""Planner node: build an execution plan from definition output."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from agent.core.llm_client import invoke_llm
from agent.graph.state import AgentState
from agent.prompts.planner_prompt import build_prompt

logger = logging.getLogger(__name__)


class _ExecutionStep(BaseModel):
    step_id: int = Field(description="Step number starting from 1.")
    description: str = Field(description="Natural language description for the executor.")
    action_type: Literal["query", "create", "update", "delete", "list", "search"] = Field(
        description="Execution action type."
    )
    target_file: str = Field(description="Target JSON file name.")
    target_info: dict = Field(description="Structured data needed for the step.")
    depends_on: list[int] = Field(default_factory=list, description="Dependency step ids.")
    condition: str = Field(default="", description="Optional execution condition.")


class _PlannerOutput(BaseModel):
    reasoning: str = Field(description="Reasoning for the produced execution plan.")
    execution_plan: list[_ExecutionStep] = Field(description="Ordered execution steps.")


_BULK_TARGET_FILE_MAP = {
    "actor": "Actors.json",
    "enemy": "Enemies.json",
    "item": "Items.json",
    "weapon": "Weapons.json",
    "armor": "Armors.json",
    "class": "Classes.json",
    "state": "States.json",
    "element": "System.json",
}

_BULK_TARGET_ALIASES = {
    "actors": "actor",
    "enemies": "enemy",
    "items": "item",
    "weapons": "weapon",
    "armors": "armor",
    "classes": "class",
    "states": "state",
}

_EXPLICIT_TARGET_INFO_KEYS = frozenset(
    {
        "actor_id",
        "actorid",
        "actor_name",
        "old_name",
        "oldname",
        "new_name",
        "newname",
        "name",
        "class_id",
        "classid",
        "class_name",
        "enemy_id",
        "enemyid",
        "enemy_name",
        "item_id",
        "itemid",
        "item_name",
        "weapon_id",
        "weaponid",
        "weapon_name",
        "armor_id",
        "armorid",
        "armor_name",
        "state_id",
        "stateid",
        "state_name",
        "skill_id",
        "skillid",
        "skill_name",
    }
)


def _normalize_bulk_target_name(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return _BULK_TARGET_ALIASES.get(raw, raw)


def _extract_bulk_update_modifications(
    modifications: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    bulk_updates: dict[str, list[dict[str, Any]]] = {}

    for modification in modifications:
        if not isinstance(modification, dict):
            continue
        if str(modification.get("type") or "").strip().lower() != "update":
            continue

        params = modification.get("params")
        if not isinstance(params, dict):
            continue

        selector = params.get("selector")
        updates = params.get("updates")
        if not (isinstance(selector, dict) and selector.get("mode") == "all"):
            continue
        if not isinstance(updates, dict) or not updates:
            continue

        target_name = _normalize_bulk_target_name(modification.get("target"))
        target_file = _BULK_TARGET_FILE_MAP.get(target_name)
        if not target_file:
            continue

        bulk_updates.setdefault(target_file, []).append(
            {
                "selector": dict(selector),
                "updates": dict(updates),
            }
        )

    return bulk_updates


def _has_explicit_target_identity(target_info: dict[str, Any]) -> bool:
    for key, value in target_info.items():
        lowered_key = str(key).strip().lower()
        if lowered_key not in _EXPLICIT_TARGET_INFO_KEYS:
            continue
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return True
    return False


def _restore_bulk_updates_from_definition(
    execution_plan: list[dict[str, Any]],
    modifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    bulk_updates = _extract_bulk_update_modifications(modifications)
    if not bulk_updates:
        return execution_plan

    restored_plan: list[dict[str, Any]] = []
    for step in execution_plan:
        if not isinstance(step, dict):
            restored_plan.append(step)
            continue

        if str(step.get("action_type") or "").strip().lower() != "update":
            restored_plan.append(step)
            continue

        target_file = str(step.get("target_file") or "").strip()
        candidates = bulk_updates.get(target_file)
        if not candidates or len(candidates) != 1:
            restored_plan.append(step)
            continue

        target_info = step.get("target_info")
        if not isinstance(target_info, dict):
            target_info = {}

        selector = target_info.get("selector")
        if isinstance(selector, dict) and selector.get("mode") == "all":
            restored_plan.append(step)
            continue
        if _has_explicit_target_identity(target_info):
            restored_plan.append(step)
            continue

        bulk_spec = candidates[0]
        merged_updates = dict(bulk_spec["updates"])
        if isinstance(target_info.get("updates"), dict):
            merged_updates.update(target_info["updates"])

        restored_target_info = dict(target_info)
        restored_target_info["selector"] = dict(bulk_spec["selector"])
        restored_target_info["updates"] = merged_updates

        restored_step = dict(step)
        restored_step["target_info"] = restored_target_info
        restored_plan.append(restored_step)

    return restored_plan


async def planner(state: AgentState) -> dict:
    """Build an execution plan from the current agent state."""
    _t0 = time.perf_counter()
    logger.info("=== Planner START ===")
    logger.info(
        "[Planner] input state | intent=%s | target_files=%s",
        state.get("intent"),
        state.get("target_files"),
    )
    logger.debug("[Planner] modifications=%s", state.get("modifications"))
    logger.debug("[Planner] extracted_ids=%s", state.get("extracted_ids"))
    logger.debug("[Planner] user_input=%s", state.get("user_input"))

    modifications = state.get("modifications")
    if not isinstance(modifications, list):
        modifications = []

    messages = build_prompt(state)
    logger.debug(
        "[Planner] prompt built | messages=%d | human_len=%d",
        len(messages),
        len(messages[-1].content) if messages else 0,
    )

    try:
        logger.info("[Planner] LLM invocation start")
        result = cast(_PlannerOutput, await invoke_llm(messages, structured_output=_PlannerOutput))
        execution_plan = [step.model_dump() for step in result.execution_plan]
        execution_plan = _restore_bulk_updates_from_definition(execution_plan, modifications)

        logger.info(
            "[Planner] LLM invocation success | steps=%d | reasoning=%s",
            len(execution_plan),
            result.reasoning,
        )
        try:
            plan_json = json.dumps(execution_plan, ensure_ascii=False, default=str)
            max_len = 16000
            if len(plan_json) > max_len:
                plan_json = plan_json[:max_len] + f"... (truncated, full_len={len(plan_json)})"
            logger.info("[Planner] execution_plan JSON: %s", plan_json)
        except (TypeError, ValueError) as dump_err:
            logger.warning("[Planner] execution_plan JSON logging failed: %s", dump_err)

        for step in execution_plan:
            logger.debug(
                "[Planner] step %d | action=%s | file=%s | depends_on=%s | condition=%s | desc=%s",
                step["step_id"],
                step["action_type"],
                step["target_file"],
                step["depends_on"],
                step["condition"] or "(none)",
                step["description"],
            )
    except Exception as exc:
        logger.error("[Planner] LLM invocation failed: %s", exc, exc_info=True)
        execution_plan = []

    logger.info("[Planner] end | returned_steps=%d", len(execution_plan))
    logger.info(
        "=== Planner END (elapsed=%.2fs, steps=%d) ===",
        time.perf_counter() - _t0,
        len(execution_plan),
    )
    return {"execution_plan": execution_plan}
