#!/usr/bin/env bash
# Re:Verse — EC2 호스트(도커 밖) 디스크·부하 모니터링 → Discord 웹훅
#
# FastAPI/컨테이너 내부가 아니라 리눅스 호스트에서 cron으로 실행합니다.
#
# 필수: DISCORD_INFRA_WEBHOOK_URL (환경 변수 또는 설정 파일)
# 선택: DISK_THRESHOLD (기본 80), LOAD_FACTOR (기본 0.90)
#
# 설정 파일(있으면 첫 번째로 발견된 것만 source):
#   $MONITOR_ENV_FILE, /etc/re-verse/monitor.env, $HOME/.config/re-verse/monitor.env
#
# cron 예:
#   0 * * * * . $HOME/.config/re-verse/monitor.env; /home/ubuntu/Re-Verse/scripts/ec2_host_monitor.sh >>/tmp/re-verse-monitor.log 2>&1

set -u

SCRIPT_NAME="ec2_host_monitor.sh"

_load_env_files() {
  local f
  for f in "${MONITOR_ENV_FILE:-}" "/etc/re-verse/monitor.env" "${HOME}/.config/re-verse/monitor.env"; do
    [[ -z "$f" ]] && continue
    [[ -f "$f" ]] || continue
    # shellcheck disable=SC1090
    source "$f"
    break
  done
}

_load_env_files

WEBHOOK_URL="${DISCORD_INFRA_WEBHOOK_URL:-}"
DISK_THRESHOLD="${DISK_THRESHOLD:-80}"
LOAD_FACTOR="${LOAD_FACTOR:-0.90}"

if [[ -z "$WEBHOOK_URL" ]]; then
  echo "[$SCRIPT_NAME] DISCORD_INFRA_WEBHOOK_URL 이 비어 있어 종료합니다." >&2
  exit 0
fi

DISK_PCT=$(df -P / 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5}')
if [[ -z "${DISK_PCT:-}" || ! "$DISK_PCT" =~ ^[0-9]+$ ]]; then
  echo "[$SCRIPT_NAME] 디스크 사용률을 읽지 못했습니다." >&2
  exit 1
fi

CORES=$(nproc 2>/dev/null || echo 1)
[[ "$CORES" =~ ^[0-9]+$ ]] || CORES=1
LOAD1=$(awk '{print $1}' /proc/loadavg 2>/dev/null || echo 0)

DISK_ALERT=0
[[ "$DISK_PCT" -ge "$DISK_THRESHOLD" ]] && DISK_ALERT=1

LOAD_ALERT=0
if awk -v L="$LOAD1" -v C="$CORES" -v F="$LOAD_FACTOR" 'BEGIN { exit !(L+0 >= (C+0) * (F+0)) }'; then
  LOAD_ALERT=1
fi

if [[ "$DISK_ALERT" -eq 0 && "$LOAD_ALERT" -eq 0 ]]; then
  exit 0
fi

HOSTNAME=$(hostname 2>/dev/null || echo unknown)

if ! command -v python3 >/dev/null 2>&1; then
  echo "[$SCRIPT_NAME] python3 가 필요합니다 (JSON 페이로드 생성)." >&2
  exit 1
fi

export _HM_HOSTNAME="$HOSTNAME"
export _HM_DISK_PCT="$DISK_PCT"
export _HM_CORES="$CORES"
export _HM_LOAD1="$LOAD1"
export _HM_DISK_TH="$DISK_THRESHOLD"
export _HM_LOAD_FACTOR="$LOAD_FACTOR"
export _HM_DISK_ALERT="$DISK_ALERT"
export _HM_LOAD_ALERT="$LOAD_ALERT"

PAYLOAD=$(
  python3 <<'PY'
import json
import os

h = os.environ.get("_HM_HOSTNAME", "unknown")
d = int(os.environ["_HM_DISK_PCT"])
c = int(os.environ["_HM_CORES"])
l = float(os.environ["_HM_LOAD1"])
dt = int(os.environ["_HM_DISK_TH"])
lf = float(os.environ["_HM_LOAD_FACTOR"])
da = int(os.environ["_HM_DISK_ALERT"])
la = int(os.environ["_HM_LOAD_ALERT"])

body = {
    "embeds": [
        {
            "title": "EC2 리소스 경고",
            "color": 16711680,
            "description": (
                f"호스트 `{h}` — 디스크≥{dt}% 또는 1분 부하≥코어×{lf} 조건을 만족했습니다."
            ),
            "fields": [
                {"name": "Disk (/)", "value": f"**{d}%**", "inline": True},
                {"name": "Load (1m) / cores", "value": f"**{l}** / {c}", "inline": True},
                {
                    "name": "Triggered",
                    "value": f"Disk: {'YES' if da else 'no'} | Load: {'YES' if la else 'no'}",
                    "inline": False,
                },
            ],
            "footer": {"text": "Re:Verse host monitor (not FastAPI container)"},
        }
    ]
}
print(json.dumps(body, ensure_ascii=False))
PY
)

if ! curl -fsS -H "Content-Type: application/json" -X POST -d "$PAYLOAD" "$WEBHOOK_URL" >/dev/null; then
  echo "[$SCRIPT_NAME] Discord 웹훅 전송 실패" >&2
  exit 1
fi

echo "[$SCRIPT_NAME] 알림 전송 완료 (disk=${DISK_PCT}% load=${LOAD1} cores=${CORES})"
