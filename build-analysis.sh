#!/usr/bin/env bash
set -Eeuo pipefail
export LANG=en_US.UTF-8

REPO_DIR="${REPO_DIR:-$HOME/Re-Verse}"
PROFILE="${PROFILE:-backend}"
OUT_DIR="${OUT_DIR:-$REPO_DIR/build-analysis}"
TS="$(date +%F-%H%M%S)"

mkdir -p "$OUT_DIR/raw" "$OUT_DIR/summary"
cd "$REPO_DIR" || exit 1

echo "[1/7] 시스템/도커 정보 수집"
{
  date; uname -a; docker version 2>&1 || true
  docker info 2>&1 | head -80 || true
} >"$OUT_DIR/summary/env-$TS.txt" 2>&1

echo "[2/7] Git/compose 상태 기록"
{
  git rev-parse HEAD 2>&1 || true
  git status --short 2>&1 || true
  docker compose -f docker-compose.yml -f docker-compose.prod.yml config 2>&1 || true
} >"$OUT_DIR/summary/context-$TS.txt" 2>&1

echo "[3/7] BuildKit 활성화"
export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

SLOW_LOG="$OUT_DIR/raw/slow-$TS.log"
FAST_LOG="$OUT_DIR/raw/fast-$TS.log"

echo "[4/7] 첫 번째 빌드(콜드/캐시 미스 가능)"
START1=$(date +%s)
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --no-cache --progress=plain "$PROFILE" >"$SLOW_LOG" 2>&1 || true
END1=$(date +%s)
echo "slow_build_seconds=$((END1-START1))" | tee -a "$SLOW_LOG"

echo "[5/7] 두 번째 빌드(웜/캐시 히트 가능)"
START2=$(date +%s)
docker compose -f docker-compose.yml -f docker-compose.prod.yml build --progress=plain "$PROFILE" >"$FAST_LOG" 2>&1 || true
END2=$(date +%s)
echo "fast_build_seconds=$((END2-START2))" | tee -a "$FAST_LOG"

echo "[6/7] 핵심 구간 요약 추출"
SUMMARY_FILE="$OUT_DIR/summary/compare-$TS.txt"
{
  echo "slow: $SLOW_LOG"; echo "fast: $FAST_LOG"
  echo "=== build wall time (seconds) ==="
  grep -hE "slow_build_seconds|fast_build_seconds" "$SLOW_LOG" "$FAST_LOG" 2>/dev/null || true
  echo "=== CACHED line count ==="
  echo -n "slow: "; grep -c "CACHED" "$SLOW_LOG" 2>/dev/null || echo 0
  echo -n "fast: "; grep -c "CACHED" "$FAST_LOG" 2>/dev/null || echo 0
  echo "=== heavy-step markers (slow) ==="
  grep -nE "git clone|npm|apt-get|uv sync|pull|exporting|DONE|ERROR" "$SLOW_LOG" 2>/dev/null | head -100 || true
  echo "=== heavy-step markers (fast) ==="
  grep -nE "git clone|npm|apt-get|uv sync|pull|exporting|DONE|ERROR" "$FAST_LOG" 2>/dev/null | head -100 || true
  echo "=== docker builder du ==="
  docker builder du 2>&1 || true
  echo "=== docker system df ==="
  docker system df 2>&1 || true
} >"$SUMMARY_FILE" 2>&1

echo "[7/7] 완료"
