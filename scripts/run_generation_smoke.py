"""Full Generation 워크플로우 스모크 테스트 — 단계별 로그 수집.

Usage:
    uv run python scripts/run_generation_smoke.py [--phase assets|maps|full]
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

# ── 로깅 설정 (DEBUG 수준, 파일+콘솔) ─────────────────────────────────────────

LOG_PATH = Path("logs/smoke_test.log")
LOG_PATH.parent.mkdir(exist_ok=True)

fmt = "%(asctime)s %(levelname)-8s %(name)-45s %(message)s"
datefmt = "%H:%M:%S"

logging.basicConfig(
    level=logging.DEBUG,
    format=fmt,
    datefmt=datefmt,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8"),
    ],
)

# LangChain / httpx 로그는 WARNING 이상만
for noisy in ("httpx", "httpcore", "openai", "langchain", "langsmith", "urllib3"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger("smoke_test")

# ─────────────────────────────────────────────────────────────────────────────

PHASE = "assets"  # default
if "--phase" in sys.argv:
    idx = sys.argv.index("--phase")
    PHASE = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else "assets"

PHASE_LIMIT_MAP = {
    "assets": "assets",
    "maps": "maps",
    "full": None,
}
phase_limit = PHASE_LIMIT_MAP.get(PHASE, "assets")

PROMPT = "마법사 왕국을 배경으로 한 짧은 RPG. 마법사 주인공이 어둠의 마왕을 쓰러뜨리는 이야기."


async def main() -> None:
    logger.info("=" * 70)
    logger.info("스모크 테스트 시작: phase=%s, phase_limit=%s", PHASE, phase_limit)
    logger.info("프롬프트: %s", PROMPT)
    logger.info("=" * 70)

    # import after logging is configured
    from agent.generation.progress import subscribe_generation_events
    from agent.generation.workflow import run_generation_workflow

    gen_id = f"smoke_{int(time.time())}"
    t_start = time.perf_counter()

    # WebSocket 이벤트 수집 태스크
    events: list[dict] = []

    async def collect_events() -> None:
        async for evt in subscribe_generation_events(gen_id):
            events.append(evt)
            etype = evt.get("type", "?")
            phase = evt.get("phase", "")
            pct = evt.get("progress", "")
            msg = evt.get("message", "") or evt.get("summary", "")
            logger.info("[WS] %-28s phase=%-15s progress=%-4s %s", etype, phase, pct, msg)
            if etype in ("completed", "completed_with_warnings", "error"):
                break

    # 이벤트 수집과 워크플로우 병렬 실행
    event_task = asyncio.create_task(collect_events())

    try:
        final_state = await run_generation_workflow(
            prompt=PROMPT,
            game_id="smoke_game_001",
            generation_id=gen_id,
            phase_limit=phase_limit,  # type: ignore[arg-type]
        )
    except Exception as e:
        logger.exception("워크플로우 실행 중 예외: %s", e)
        event_task.cancel()
        return

    elapsed = time.perf_counter() - t_start
    await asyncio.sleep(0.3)  # 마지막 WS 이벤트 flush 대기
    event_task.cancel()

    # ── 결과 분석 ────────────────────────────────────────────────────────────

    logger.info("=" * 70)
    logger.info("완료: elapsed=%.1fs", elapsed)
    logger.info("completed_phases: %s", final_state.get("completed_phases"))
    logger.info("is_success: %s", final_state.get("is_success"))
    logger.info("validation_passed: %s", final_state.get("validation_passed"))

    errors = final_state.get("validation_errors") or []
    warnings = final_state.get("validation_warnings") or []
    if errors:
        logger.warning("검증 오류 %d건:", len(errors))
        for e in errors:
            logger.warning("  %s", e)
    if warnings:
        logger.info("검증 경고 %d건:", len(warnings))
        for w in warnings:
            logger.info("  %s", w)

    # ── 생성된 파일 목록 ──────────────────────────────────────────────────────
    final_project = final_state.get("final_project") or {}
    logger.info("생성된 파일 %d개:", len(final_project))
    for fname, data in final_project.items():
        if isinstance(data, list):
            logger.info("  %-25s  [list]  len=%d", fname, len(data))
        elif isinstance(data, dict):
            keys = ", ".join(list(data.keys())[:5])
            logger.info("  %-25s  {dict}  keys=%s...", fname, keys)

    # ── 에셋 요약 ────────────────────────────────────────────────────────────
    for asset_file in ["Actors.json", "Classes.json", "Enemies.json", "Troops.json"]:
        data = final_project.get(asset_file, [])
        items = [x for x in data if x is not None]
        names = [x.get("name", "?") for x in items]
        logger.info("%-20s: %d개 → %s", asset_file, len(items), names)

    # ── 맵 요약 ─────────────────────────────────────────────────────────────
    map_specs = final_state.get("map_specs") or []
    if map_specs:
        logger.info("맵 %d개:", len(map_specs))
        for ms in map_specs:
            tile_data = (final_state.get("map_tiles") or {}).get(ms.map_id, [])
            compiled = (final_state.get("compiled_events") or {}).get(ms.map_id, [])
            logger.info(
                "  Map%03d %-20s  type=%-8s  tiles=%d  events=%d",
                ms.map_id,
                ms.name,
                ms.map_type,
                len(tile_data),
                len(compiled),
            )

    # ── 스위치 요약 ──────────────────────────────────────────────────────────
    switch_table = final_state.get("switch_table")
    if switch_table:
        logger.info(
            "스위치 %d개: %s",
            len(switch_table.switches),
            list(switch_table.switches.keys())[:10],
        )

    # ── GameSpec 요약 ────────────────────────────────────────────────────────
    game_spec = final_state.get("game_spec")
    if game_spec:
        logger.info("GameSpec: title=%s", game_spec.title)
        logger.info("  캐릭터: %s", [c.name for c in game_spec.characters])
        logger.info("  맵: %s", [m.name for m in game_spec.maps])
        logger.info("  적: %s", [e.name for e in game_spec.enemies])

    # ── WS 이벤트 타임라인 ────────────────────────────────────────────────────
    logger.info("WS 이벤트 %d개 수신", len(events))

    # ── JSON 덤프 (디버그용) ──────────────────────────────────────────────────
    dump_path = Path(f"logs/smoke_{PHASE}_state.json")
    try:
        safe_state = {
            k: v
            for k, v in final_state.items()
            if k not in ("map_tiles", "final_project")  # 타일 데이터 제외 (너무 큼)
        }
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(safe_state, f, ensure_ascii=False, indent=2, default=str)
        logger.info("상태 덤프 저장: %s", dump_path)
    except Exception as e:
        logger.warning("상태 덤프 실패: %s", e)

    logger.info("=" * 70)
    logger.info("로그 저장: %s", LOG_PATH)


if __name__ == "__main__":
    asyncio.run(main())
