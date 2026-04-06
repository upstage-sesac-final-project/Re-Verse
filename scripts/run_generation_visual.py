"""Full Generation 워크플로우 시각화 러너.

Usage:
    uv run python scripts/run_generation_visual.py [assets|maps|full]
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table
from rich.text import Text

console = Console()

# ── 로깅: WARNING 이상만 콘솔, DEBUG 이상은 파일에 ─────────────────────────
LOG_PATH = Path("logs/visual_test.log")
LOG_PATH.parent.mkdir(exist_ok=True)
file_handler = logging.FileHandler(LOG_PATH, mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s %(message)s"))
logging.basicConfig(level=logging.DEBUG, handlers=[file_handler])
for noisy in ("httpx", "httpcore", "openai", "langchain", "langsmith", "urllib3", "asyncio"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

# ─────────────────────────────────────────────────────────────────────────────

PHASE = sys.argv[1] if len(sys.argv) > 1 else "full"
PHASE_LIMIT_MAP = {"assets": "assets", "maps": "maps", "full": None}
phase_limit = PHASE_LIMIT_MAP.get(PHASE, None)

PROMPT = "마법사 왕국을 배경으로 한 짧은 RPG. 마법사 주인공이 어둠의 마왕을 쓰러뜨리는 이야기."

PHASE_ORDER = [
    ("spec", "A. 게임 기획", "cyan"),
    ("planning", "B. 에셋 계획", "blue"),
    ("assets", "C. 에셋 생성", "blue"),
    ("map_design", "D. 맵 설계", "magenta"),
    ("tile_generation", "E. 타일 생성", "magenta"),
    ("event_plan", "F. 이벤트 기획", "yellow"),
    ("event_compile", "G. 이벤트 컴파일", "yellow"),
    ("integration", "H. 프로젝트 조립", "green"),
    ("validation", "I. 검증", "green"),
]

ws_events: list[dict] = []
completed_phases: list[str] = []
phase_times: dict[str, float] = {}
_phase_start: dict[str, float] = {}


def _phase_bar() -> Table:
    t = Table.grid(padding=(0, 1))
    for key, label, color in PHASE_ORDER:
        if key in completed_phases:
            icon = f"[bold {color}]✓[/bold {color}]"
            elapsed = phase_times.get(key, 0)
            txt = f"[{color}]{label}[/{color}] [dim]{elapsed:.1f}s[/dim]"
        elif key == _current_phase():
            icon = "[bold yellow]⟳[/bold yellow]"
            txt = f"[bold yellow]{label}[/bold yellow]"
        else:
            icon = "[dim]·[/dim]"
            txt = f"[dim]{label}[/dim]"
        t.add_row(icon, txt)
    return t


def _current_phase() -> str:
    done = set(completed_phases)
    for key, _, _ in PHASE_ORDER:
        if key not in done:
            return key
    return ""


async def main() -> None:
    from agent.generation.progress import subscribe_generation_events
    from agent.generation.workflow import run_generation_workflow

    gen_id = f"vis_{int(time.time())}"
    t_start = time.perf_counter()

    console.rule(f"[bold]Full Generation — phase=[cyan]{PHASE}[/cyan]")
    console.print(f"[dim]프롬프트:[/dim] {PROMPT}\n")

    # WebSocket 이벤트 수집
    async def collect_events() -> None:
        async for evt in subscribe_generation_events(gen_id):
            ws_events.append(evt)
            etype = evt.get("type", "")
            phase = evt.get("phase", "")
            if etype == "phase_complete" and phase:
                completed_phases.append(phase)
                phase_times[phase] = time.perf_counter() - _phase_start.get(phase, t_start)
            if etype == "progress" and phase and phase not in _phase_start:
                _phase_start[phase] = time.perf_counter()
            if etype in ("completed", "completed_with_warnings", "error"):
                break

    event_task = asyncio.create_task(collect_events())

    # Progress bar
    progress = Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
        transient=True,
    )

    with progress:
        task_id = progress.add_task("[cyan]생성 중...", total=100)

        async def _run() -> None:
            nonlocal final_state
            final_state = await run_generation_workflow(
                prompt=PROMPT,
                game_id="vis_game_001",
                generation_id=gen_id,
                phase_limit=phase_limit,  # type: ignore[arg-type]
            )

        async def _update_progress() -> None:
            last_pct = 0
            while True:
                for evt in ws_events:
                    pct = evt.get("progress")
                    if isinstance(pct, int) and pct > last_pct:
                        last_pct = pct
                        desc = evt.get("message", "생성 중...")[:60]
                        progress.update(task_id, completed=pct, description=f"[cyan]{desc}")
                await asyncio.sleep(0.2)

        final_state = {}
        updater = asyncio.create_task(_update_progress())
        await _run()
        updater.cancel()
        progress.update(task_id, completed=100)

    await asyncio.sleep(0.3)
    event_task.cancel()
    elapsed = time.perf_counter() - t_start

    # ── 결과 렌더링 ────────────────────────────────────────────────────────

    is_success = final_state.get("is_success", False)
    errors = final_state.get("validation_errors") or []
    warnings = final_state.get("validation_warnings") or []
    game_spec = final_state.get("game_spec")
    map_specs = final_state.get("map_specs") or []
    final_project = final_state.get("final_project") or {}
    switch_table = final_state.get("switch_table")
    map_tiles = final_state.get("map_tiles") or {}
    compiled_events = final_state.get("compiled_events") or {}

    status_color = "green" if is_success else "yellow"
    status_label = "✓ 성공" if is_success else "⚠ 부분 성공"
    console.rule(f"[bold {status_color}]{status_label}  {elapsed:.1f}s")

    # ── 노드 진행 현황 ────────────────────────────────────────────────────
    console.print(Panel(_phase_bar(), title="[bold]노드 실행 현황", border_style="dim"))

    # ── GameSpec ─────────────────────────────────────────────────────────
    if game_spec:
        gs_table = Table(show_header=False, box=box.SIMPLE, padding=(0, 1))
        gs_table.add_column("키", style="dim", width=10)
        gs_table.add_column("값")
        gs_table.add_row("제목", f"[bold cyan]{game_spec.title}[/bold cyan]")
        gs_table.add_row("테마", game_spec.theme[:60])
        gs_table.add_row(
            "캐릭터",
            ", ".join(
                f"[yellow]{c.name}[/yellow]([dim]{c.class_name}[/dim])"
                for c in game_spec.characters
            ),
        )
        gs_table.add_row(
            "맵",
            ", ".join(f"[magenta]{m.name}[/magenta]([dim]{m.type}[/dim])" for m in game_spec.maps),
        )
        gs_table.add_row(
            "적", ", ".join(f"[red]{e.name}[/red][dim]({e.tier})[/dim]" for e in game_spec.enemies)
        )
        console.print(Panel(gs_table, title="[bold]게임 기획 (GameSpec)", border_style="cyan"))

    # ── 에셋 파일 ─────────────────────────────────────────────────────────
    asset_table = Table(box=box.ROUNDED, show_header=True, header_style="bold blue")
    asset_table.add_column("파일", width=22)
    asset_table.add_column("개수", justify="right", width=6)
    asset_table.add_column("내용", overflow="fold")

    ASSET_FILES = [
        ("Actors.json", "yellow"),
        ("Classes.json", "yellow"),
        ("Skills.json", "blue"),
        ("Items.json", "green"),
        ("Weapons.json", "green"),
        ("Armors.json", "green"),
        ("Enemies.json", "red"),
        ("Troops.json", "red"),
    ]
    for fname, color in ASSET_FILES:
        data = final_project.get(fname, [])
        items = [x for x in data if x is not None]
        names = ", ".join(x.get("name", "?") for x in items[:6])
        if len(items) > 6:
            names += f" +{len(items) - 6}개"
        asset_table.add_row(
            f"[{color}]{fname}[/{color}]",
            str(len(items)),
            f"[dim]{names}[/dim]",
        )
    console.print(Panel(asset_table, title="[bold]에셋 파일", border_style="blue"))

    # ── 맵 ──────────────────────────────────────────────────────────────
    if map_specs:
        map_table = Table(box=box.ROUNDED, header_style="bold magenta")
        map_table.add_column("ID", width=6, justify="right")
        map_table.add_column("이름", width=20)
        map_table.add_column("타입", width=10)
        map_table.add_column("크기", width=10, justify="right")
        map_table.add_column("타일", width=8, justify="right")
        map_table.add_column("이벤트", width=8, justify="right")
        map_table.add_column("BGM", width=12)

        MAP_COLORS = {"town": "green", "field": "cyan", "dungeon": "yellow", "boss": "red"}
        for spec in map_specs:
            color = MAP_COLORS.get(spec.map_type, "white")
            tile_data = map_tiles.get(spec.map_id, [])
            events = compiled_events.get(spec.map_id, [])
            map_table.add_row(
                str(spec.map_id),
                f"[{color}]{spec.name}[/{color}]",
                f"[{color}]{spec.map_type}[/{color}]",
                f"{spec.width}×{spec.height}",
                str(len(tile_data)),
                str(len(events)),
                f"[dim]{spec.bgm[:10] if spec.bgm else '-'}[/dim]",
            )
        console.print(Panel(map_table, title="[bold]맵 파일 (Map*.json)", border_style="magenta"))

    # ── 이벤트 상세 ──────────────────────────────────────────────────────
    if compiled_events and any(compiled_events.values()):
        evt_table = Table(box=box.SIMPLE_HEAD, header_style="bold yellow")
        evt_table.add_column("맵", width=18)
        evt_table.add_column("이벤트", width=18)
        evt_table.add_column("타입", width=12)
        evt_table.add_column("위치", width=8, justify="right")
        evt_table.add_column("페이지", width=6, justify="right")

        TYPE_COLORS = {
            "npc": "cyan",
            "transfer": "green",
            "chest": "yellow",
            "battle": "red",
            "shop": "blue",
            "ending": "magenta",
        }
        for spec in map_specs:
            evts = compiled_events.get(spec.map_id, [])
            for ev in evts:
                name = ev.get("name", "?")
                pages = ev.get("pages", [])
                # 타입 추측: 커맨드 코드로
                codes = {cmd.get("code") for pg in pages for cmd in pg.get("list", [])}
                if 354 in codes or 353 in codes:
                    etype = "ending"
                elif 301 in codes:
                    etype = "battle"
                elif 201 in codes:
                    etype = "transfer"
                elif 302 in codes:
                    etype = "shop"
                elif 126 in codes or 127 in codes or 128 in codes:
                    etype = "chest"
                else:
                    etype = "npc"
                color = TYPE_COLORS.get(etype, "white")
                evt_table.add_row(
                    f"[dim]{spec.name[:16]}[/dim]",
                    f"[{color}]{name[:16]}[/{color}]",
                    f"[{color}]{etype}[/{color}]",
                    f"({ev.get('x', 0)},{ev.get('y', 0)})",
                    str(len(pages)),
                )
        console.print(Panel(evt_table, title="[bold]이벤트 상세", border_style="yellow"))

    # ── 스위치 ──────────────────────────────────────────────────────────
    if switch_table and switch_table.switches:
        sw_items = [
            f"[cyan]{name}[/cyan][dim]={sid}[/dim]"
            for name, sid in sorted(switch_table.switches.items(), key=lambda x: x[1])
        ]
        sw_text = Text()
        for i, item in enumerate(sw_items):
            sw_text.append_text(Text.from_markup(item))
            if i < len(sw_items) - 1:
                sw_text.append("  ")
        console.print(
            Panel(
                sw_text, title=f"[bold]스위치 ({len(switch_table.switches)}개)", border_style="cyan"
            )
        )

    # ── 생성 파일 목록 ────────────────────────────────────────────────────
    file_cols = []
    for fname in final_project:
        data = final_project[fname]
        if isinstance(data, list):
            cnt = len([x for x in data if x is not None])
            file_cols.append(f"[green]✓[/green] [bold]{fname}[/bold] [dim]({cnt})[/dim]")
        else:
            file_cols.append(f"[green]✓[/green] [bold]{fname}[/bold]")
    console.print(
        Panel(
            Columns(file_cols, equal=True, padding=(0, 1)),
            title=f"[bold]생성된 파일 ({len(final_project)}개)",
            border_style="green",
        )
    )

    # ── 검증 결과 ─────────────────────────────────────────────────────────
    if errors:
        err_text = "\n".join(f"[red]✗ {e}[/red]" for e in errors)
        console.print(Panel(err_text, title="[bold red]검증 오류", border_style="red"))
    if warnings:
        warn_text = "\n".join(f"[yellow]⚠ {w}[/yellow]" for w in warnings)
        console.print(Panel(warn_text, title="[bold yellow]검증 경고", border_style="yellow"))
    if not errors and not warnings:
        console.print(
            Panel("[green bold]검증 완전 통과 — 오류 없음[/green bold]", border_style="green")
        )

    # ── 최종 요약 ─────────────────────────────────────────────────────────
    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="dim", width=14)
    summary.add_column()
    summary.add_row("총 소요", f"[bold]{elapsed:.1f}s[/bold]")
    summary.add_row(
        "완료 노드",
        " → ".join(f"[green]{p}[/green]" for p in final_state.get("completed_phases", [])),
    )
    summary.add_row("WS 이벤트", str(len(ws_events)))
    summary.add_row("생성 파일", f"[bold]{len(final_project)}개[/bold]")
    summary.add_row("로그 파일", str(LOG_PATH))
    console.print(
        Panel(summary, title=f"[bold {status_color}]{status_label}", border_style=status_color)
    )


if __name__ == "__main__":
    asyncio.run(main())
