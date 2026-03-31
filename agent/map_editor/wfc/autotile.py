"""A1/A2 오토타일 shape 자동 계산.

MZ_SampleMap 42개 맵 실측 역공학으로 확인한 실제 shape 인코딩.

━━━ 핵심 개념 ━━━
- A2 섹션은 tile_id 2816에서 시작, 48개씩 그룹
  · 풀밭 그룹:  2816~2863 (48개)  → section_base = 2816
  · 모래 그룹:  2864~2911         → section_base = 2864
  · 흙 그룹:    2912~2959         → section_base = 2912
- A1 섹션은 tile_id 2048에서 시작
  · 깊은물:     2048~2095         → section_base = 2048

- tile_id = section_base + shape_offset (0~47)
- shape_offset 0 = 완전 내부 (기본 타일, ex. 2816 = 풀밭 기본)

━━━ shape_offset 테이블 (실측 기반) ━━━
4방향 (N,S,E,W) 이웃이 같은 그룹인지 여부:
  (1,1,1,1) → 대각선 inner corner 계산 (0~15)
  (1,1,1,0) → 16   (1,1,0,1) → 24
  (1,0,1,1) → 28   (0,1,1,1) → 20
  (1,1,0,0) → 32   (0,0,1,1) → 33
  (1,0,1,0) → 40   (1,0,0,1) → 38
  (0,1,1,0) → 34   (0,1,0,1) → 36
  (1,0,0,0) → 44   (0,1,0,0) → 42
  (0,0,1,0) → 43   (0,0,0,1) → 45
  (0,0,0,0) → 46   (완전 고립)

inner corner (4방향 모두 같을 때):
  NW missing → +1,  NE missing → +2
  SE missing → +4,  SW missing → +8
  모두 같음  →  0  (완전 내부)
"""

_TILE_ID_A1 = 2048
_TILE_ID_A2 = 2816
_TILE_ID_A3 = 4352  # A1/A2 경계 끝

# ── 4방향 → shape_offset 룩업 테이블 ──────────────────────────────────────
_CARDINAL_SHAPE: dict[tuple[bool, bool, bool, bool], int] = {
    # (N, S, E, W)
    (False, False, False, False): 46,
    (True, False, False, False): 44,
    (False, True, False, False): 42,
    (False, False, True, False): 43,
    (False, False, False, True): 45,
    (True, True, False, False): 32,
    (True, False, True, False): 40,
    (True, False, False, True): 38,
    (False, True, True, False): 34,
    (False, True, False, True): 36,
    (False, False, True, True): 33,
    (True, True, True, False): 16,
    (True, True, False, True): 24,
    (True, False, True, True): 28,
    (False, True, True, True): 20,
    # (True, True, True, True) → inner corner 계산
}


def _is_a12(tile_id: int) -> bool:
    return _TILE_ID_A1 <= tile_id < _TILE_ID_A3


def _get_section_base(tile_id: int) -> int:
    """tile_id가 속한 오토타일 그룹의 section_base를 반환한다.

    같은 그룹의 타일은 항상 같은 section_base를 가진다.
      2816 → 2816,  2832 → 2816,  2863 → 2816  (모두 풀밭 그룹)
      2864 → 2864                               (모래 그룹)
    """
    if tile_id >= _TILE_ID_A2:
        return _TILE_ID_A2 + ((tile_id - _TILE_ID_A2) // 48) * 48
    return _TILE_ID_A1 + ((tile_id - _TILE_ID_A1) // 48) * 48


def _calc_shape(
    n: bool,
    s: bool,
    e: bool,
    w: bool,
    nw: bool,
    ne: bool,
    sw: bool,
    se: bool,
) -> int:
    """8방향 이웃 동일 여부로 shape_offset(0~47)을 반환한다."""
    cardinal = (n, s, e, w)

    if cardinal != (True, True, True, True):
        return _CARDINAL_SHAPE[cardinal]

    # 4방향 모두 같음 → 대각선 inner corner 비트
    inner = (0 if nw else 1) | (0 if ne else 2) | (0 if se else 4) | (0 if sw else 8)
    return inner  # 0(완전 내부) ~ 15


def apply_autotile_shapes(
    layer0: list[int],
    width: int,
    height: int,
) -> list[int]:
    """layer 0 데이터에서 A1/A2 오토타일의 shape를 올바르게 재계산한다.

    지형 페인팅 후 이 함수를 실행하면 RPG Maker MZ가
    경계를 자연스러운 전환 그래픽으로 렌더링한다.
    A1/A2 이외 타일(A3/A4/A5/B-E)은 변경하지 않는다.
    """
    result = layer0[:]

    def get_section_base_at(x: int, y: int) -> int:
        """(x,y) 위치 타일의 section_base. 범위 밖/비-A12 → 고유 음수."""
        if x < 0 or x >= width or y < 0 or y >= height:
            return -1
        tid = layer0[y * width + x]
        if _is_a12(tid):
            return _get_section_base(tid)
        return -(tid + 2)  # 비-A12: 절대 같지 않도록 고유 음수

    for y in range(height):
        for x in range(width):
            tid = layer0[y * width + x]
            if not _is_a12(tid):
                continue

            base = _get_section_base(tid)

            n = get_section_base_at(x, y - 1) == base
            s = get_section_base_at(x, y + 1) == base
            e = get_section_base_at(x + 1, y) == base
            w = get_section_base_at(x - 1, y) == base
            nw = get_section_base_at(x - 1, y - 1) == base
            ne = get_section_base_at(x + 1, y - 1) == base
            sw = get_section_base_at(x - 1, y + 1) == base
            se = get_section_base_at(x + 1, y + 1) == base

            shape = _calc_shape(n, s, e, w, nw, ne, sw, se)
            result[y * width + x] = base + shape

    return result
