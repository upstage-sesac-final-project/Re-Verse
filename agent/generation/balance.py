"""전투 시뮬레이션 + 밸런스 검증.

simulate_battle(): 플레이어 vs 적 1대1 시뮬레이션 (I 노드 경고용).
check_balance(): final_project 전체 밸런스 검사.
canonical: docs/The_world/sprint_plan.md §Phase 5
"""

from dataclasses import dataclass


@dataclass
class BattleResult:
    player_survived: bool
    turns: int
    player_hp_remaining: int
    enemy_hp_remaining: int


def simulate_battle(
    player_hp: int,
    player_atk: int,
    player_def: int,
    enemy_hp: int,
    enemy_atk: int,
    enemy_def: int,
    max_turns: int = 50,
) -> BattleResult:
    """플레이어-적 1대1 턴제 시뮬레이션. 플레이어 선공."""
    p_hp, e_hp = player_hp, enemy_hp
    turns = 0
    while p_hp > 0 and e_hp > 0 and turns < max_turns:
        e_hp -= max(1, player_atk - enemy_def)
        if e_hp <= 0:
            break
        p_hp -= max(1, enemy_atk - player_def)
        turns += 1
    return BattleResult(
        player_survived=p_hp > 0,
        turns=turns,
        player_hp_remaining=max(0, p_hp),
        enemy_hp_remaining=max(0, e_hp),
    )


def _estimate_player_stats(project: dict) -> tuple[int, int, int]:
    """Classes.json params Lv1 값 평균에서 hp/atk/def 추정.

    params 배열 구조: [hp_arr, mp_arr, atk_arr, def_arr, ...]
    """
    classes = project.get("Classes.json", [])
    hp_vals: list[int] = []
    atk_vals: list[int] = []
    def_vals: list[int] = []
    for cls in classes:
        if cls is None:
            continue
        params = cls.get("params", [])
        if len(params) >= 4 and len(params[0]) > 0:
            hp_vals.append(params[0][0])
            atk_vals.append(params[2][0])
            def_vals.append(params[3][0])
    if not hp_vals:
        return 150, 15, 8  # fallback 기본값
    return (
        sum(hp_vals) // len(hp_vals),
        sum(atk_vals) // len(atk_vals),
        sum(def_vals) // len(def_vals),
    )


def check_balance(project: dict) -> list[str]:
    """final_project 기반 밸런스 경고 목록 반환.

    기존 generation_validator._check_balance()를 대체하는 심화 버전.
    """
    warnings: list[str] = []
    player_hp, player_atk, player_def = _estimate_player_stats(project)

    enemies = project.get("Enemies.json", [])
    for enemy in enemies[1:]:  # index-0 null 스킵
        if enemy is None:
            continue
        params = enemy.get("params", [0] * 8)
        e_hp = params[0] if len(params) > 0 else 0
        e_atk = params[2] if len(params) > 2 else 0
        e_def = params[3] if len(params) > 3 else 0
        name = enemy.get("name", "?")

        if e_hp == 0:
            warnings.append(f"[BALANCE] {name}: HP=0")
            continue

        result = simulate_battle(player_hp, player_atk, player_def, e_hp, e_atk, e_def)
        if not result.player_survived:
            warnings.append(f"[BALANCE] {name}: 플레이어가 1대1에서 패배 (예상 {result.turns}턴)")
        elif result.turns > 20:
            warnings.append(f"[BALANCE] {name}: 전투가 너무 김 ({result.turns}턴 예상)")

    return warnings
