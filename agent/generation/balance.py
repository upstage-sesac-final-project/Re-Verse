"""전투 시뮬레이션 + 밸런스 검증 (RPG Maker MZ 실제 공식 기반).

데미지 공식: damage = max(0, a.atk * 4 - b.def * 2)
tier별 조우 레벨 기준으로 플레이어 스탯(클래스+장비) 추정 후 시뮬.

canonical: docs/The_world/BALANCE_IMPROVEMENT_PLAN.md
"""

from dataclasses import dataclass

# ── tier별 조우 레벨 ────────────────────────────────────────────────────────

_ENCOUNTER_LV: dict[str, int] = {"weak": 2, "normal": 6, "elite": 12, "boss": 18}

# tier별 시뮬 판정 기준 (1명 기준 최대 킬턴)
_MAX_KILL_TURNS: dict[str, int] = {"weak": 5, "normal": 8, "elite": 15, "boss": 25}


def _rpg_damage(atk: int, def_: int) -> int:
    """RPG Maker MZ 기본 공격 데미지 공식."""
    return max(0, atk * 4 - def_ * 2)


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
    party_size: int = 1,
    max_turns: int = 50,
) -> BattleResult:
    """플레이어 파티 vs 적 1체 턴제 시뮬레이션. 파티 선공.

    파티원 전원이 매턴 1회 공격, 적은 랜덤 1명 공격.
    """
    p_hp, e_hp = player_hp, enemy_hp
    turns = 0

    p_dmg = _rpg_damage(player_atk, enemy_def)
    e_dmg = _rpg_damage(enemy_atk, player_def)

    while p_hp > 0 and e_hp > 0 and turns < max_turns:
        # 파티 공격 (party_size명이 각 1회)
        e_hp -= p_dmg * party_size
        if e_hp <= 0:
            break
        # 적 공격 (1명에게)
        p_hp -= e_dmg
        turns += 1

    return BattleResult(
        player_survived=p_hp > 0,
        turns=turns,
        player_hp_remaining=max(0, p_hp),
        enemy_hp_remaining=max(0, e_hp),
    )


def _get_tier_from_note(enemy: dict) -> str:
    """enemy["note"]에서 tier 파싱. 예: 'tier:boss location:성' → 'boss'."""
    note = enemy.get("note", "")
    for part in note.split():
        if part.startswith("tier:"):
            return part[5:]
    return "normal"


def _interp(lv: int, lv1: int, lv20: int) -> int:
    """lv1~lv20 선형 보간."""
    return round(lv1 + (lv20 - lv1) * ((lv - 1) / 19))


def _estimate_player_at_level(project: dict, lv: int) -> tuple[int, int, int]:
    """해당 레벨의 플레이어 HP/ATK/DEF 추정 (클래스 + 장비 보정).

    Returns: (hp, atk, def)
    """
    # 클래스 평균 lv 스탯
    classes = project.get("Classes.json", [])
    hp_vals, atk_vals, def_vals = [], [], []
    for cls in classes:
        if cls is None:
            continue
        params = cls.get("params", [])
        if len(params) >= 4 and isinstance(params[0], list) and len(params[0]) >= lv:
            hp_vals.append(params[0][lv - 1])
            atk_vals.append(params[2][lv - 1])
            def_vals.append(params[3][lv - 1])

    if not hp_vals:
        # fallback: balanced 기본값 보간
        return _interp(lv, 350, 2500), _interp(lv, 12, 45), _interp(lv, 10, 40)

    base_hp = sum(hp_vals) // len(hp_vals)
    base_atk = sum(atk_vals) // len(atk_vals)
    base_def = sum(def_vals) // len(def_vals)

    # 장비 보정: 해당 레벨에 맞는 power의 무기/방어구
    weapon_atk = _estimate_best_weapon_atk(project, lv)
    armor_def = _estimate_best_armor_def(project, lv)

    return base_hp, base_atk + weapon_atk, base_def + armor_def


def _estimate_best_weapon_atk(project: dict, lv: int) -> int:
    """해당 레벨 시점에 구매 가능한 최적 무기의 ATK 보정값 추정."""
    weapons = project.get("Weapons.json", [])
    # 진행도에 맞는 power: lv/20*10
    target_power = round(lv / 20 * 10)

    best_atk = 0
    for w in weapons:
        if w is None:
            continue
        params = w.get("params", [0] * 8)
        atk = params[2] if len(params) > 2 else 0
        # price 기반으로 해당 레벨에서 구매 가능 여부 판단은 복잡하므로
        # 단순히 ATK 기준 target_power에 가장 가까운 무기 선택
        if atk <= target_power * 5 + 10:  # 대략적 상한
            best_atk = max(best_atk, atk)

    if best_atk == 0:
        # fallback: power 기반 추정
        best_atk = round(target_power * 50 * 1.0 / 10)  # sword profile

    return best_atk


def _estimate_best_armor_def(project: dict, lv: int) -> int:
    """해당 레벨 시점에 구매 가능한 최적 방어구의 DEF 보정값 추정."""
    armors = project.get("Armors.json", [])
    target_power = round(lv / 20 * 10)

    best_def = 0
    for a in armors:
        if a is None:
            continue
        params = a.get("params", [0] * 8)
        def_val = params[3] if len(params) > 3 else 0
        if def_val <= target_power * 4 + 10:
            best_def = max(best_def, def_val)

    if best_def == 0:
        best_def = round(target_power * 40 * 1.0 / 10)  # body profile

    return best_def


def check_balance(project: dict) -> list[str]:
    """final_project 기반 밸런스 경고 목록 반환.

    tier별 조우 레벨 기준으로 플레이어 스탯 추정 후 시뮬.
    """
    warnings: list[str] = []

    # 파티 인원수
    actors = project.get("Actors.json", [])
    party_size = max(1, len([a for a in actors if a is not None]))

    enemies = project.get("Enemies.json", [])
    for enemy in enemies:
        if enemy is None:
            continue
        params = enemy.get("params", [0] * 8)
        e_hp = params[0] if len(params) > 0 else 0
        e_atk = params[2] if len(params) > 2 else 0
        e_def = params[3] if len(params) > 3 else 0
        name = enemy.get("name", "?")
        tier = _get_tier_from_note(enemy)

        if e_hp == 0:
            warnings.append(f"[BALANCE] {name}: HP=0")
            continue

        # tier별 조우 레벨의 플레이어 스탯으로 시뮬
        lv = _ENCOUNTER_LV.get(tier, 6)
        p_hp, p_atk, p_def = _estimate_player_at_level(project, lv)

        result = simulate_battle(p_hp, p_atk, p_def, e_hp, e_atk, e_def, party_size=party_size)

        max_turns = _MAX_KILL_TURNS.get(tier, 10)

        if not result.player_survived:
            warnings.append(
                f"[BALANCE] {name}({tier}): 파티 {party_size}명이 lv{lv}에서 패배 ({result.turns}턴)"
            )
        elif result.turns > max_turns:
            warnings.append(
                f"[BALANCE] {name}({tier}): 전투 {result.turns}턴 (목표 {max_turns}턴 이내)"
            )

    # 무기/방어구 params 0 체크
    for w in project.get("Weapons.json", []):
        if w is None or not w.get("name"):
            continue
        params = w.get("params", [0] * 8)
        if params[2] == 0 and params[4] == 0:  # ATK=0 AND MAT=0
            warnings.append(f"[BALANCE] 무기 '{w['name']}': ATK=0, MAT=0 (장착 효과 없음)")

    for a in project.get("Armors.json", []):
        if a is None or not a.get("name"):
            continue
        params = a.get("params", [0] * 8)
        if params[3] == 0 and params[5] == 0:  # DEF=0 AND MDF=0
            warnings.append(f"[BALANCE] 방어구 '{a['name']}': DEF=0, MDF=0 (장착 효과 없음)")

    return warnings
