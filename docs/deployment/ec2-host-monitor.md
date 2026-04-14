# EC2 호스트 디스크·부하 알림 (Docker 밖)

백엔드 컨테이너와 **무관하게**, EC2 **리눅스 호스트**에서 디스크 사용률과 CPU 부하(1분 평균 부하 vs 코어 수)를 주기적으로 점검해 Discord로 알립니다.
Docker 빌드 캐시·이미지로 디스크가 찰 때 서비스 전체가 멈추는 상황을 빨리 알기 위한 용도입니다.

## 포함 파일

| 경로 | 설명 |
|------|------|
| `scripts/ec2_host_monitor.sh` | 점검 + 웹훅 전송 스크립트 |
| `scripts/monitor.env.example` | 환경 변수 템플릿 (웹훅 URL 등) |

## 동작 요약

- **디스크**: 루트 파티션 `/` 사용률이 `DISK_THRESHOLD`(기본 **80%**) 이상이면 경고.
- **부하**: 1분 평균 부하(`load1`)가 **코어 수 × LOAD_FACTOR**(기본 **0.90**) 이상이면 경고.
  (`top` 문자열 파싱 대신 `/proc/loadavg` + `nproc` 사용 — 로케일에 덜 민감함.)
- 둘 중 **하나라도** 만족하면 Discord로 embed 1건 전송.
- `DISCORD_INFRA_WEBHOOK_URL`이 비어 있으면 조용히 종료(exit 0).

## EC2에서 할 일 (최초 1회)

1. **Discord**에서 인프라/서버 모니터링용 채널을 만들고 **웹훅 URL**을 복사합니다.

2. SSH로 EC2 접속 후, 저장소 경로가 `~/Re-Verse`라고 가정합니다 (`git clone` 위치에 맞게 조정).

3. 설정 파일 생성 (비밀 보호를 위해 권한 제한 권장):

   ```bash
   mkdir -p ~/.config/re-verse
   cp ~/Re-Verse/scripts/monitor.env.example ~/.config/re-verse/monitor.env
   nano ~/.config/re-verse/monitor.env
   # DISCORD_INFRA_WEBHOOK_URL=... 만 실제 값으로 수정
   chmod 600 ~/.config/re-verse/monitor.env
   ```

4. 스크립트 실행 권한:

   ```bash
   chmod +x ~/Re-Verse/scripts/ec2_host_monitor.sh
   ```

5. **테스트** (임계값을 일부러 낮춰 알람이 오게 할 수 있음):

   ```bash
   # 한 번만 낮춰서 테스트 (예: 디스크 1%만 넘어도 울리게)
   DISK_THRESHOLD=1 DISCORD_INFRA_WEBHOOK_URL='https://...' ~/Re-Verse/scripts/ec2_host_monitor.sh
   ```

   Discord에 메시지가 오면 성공입니다. 이후 `monitor.env`에서 `DISK_THRESHOLD`를 지우거나 80으로 되돌립니다.

6. **cron 등록** (매시 정각 예시, 사용자·경로 맞게 수정):

   ```bash
   crontab -e
   ```

   다음 한 줄 추가:

   ```cron
   0 * * * * . $HOME/.config/re-verse/monitor.env; $HOME/Re-Verse/scripts/ec2_host_monitor.sh >>/tmp/re-verse-monitor.log 2>&1
   ```

## 디스크 급할 때 (알람 후 조치)

배포 워크플로에 `docker image prune -f`가 있어도 부족할 수 있습니다. EC2에서 **백업·재배포 계획 확인 후** 필요 시:

```bash
docker system prune -a -f
```

사용하지 않는 이미지·빌드 캐시를 넓게 지우므로, 다음 `docker compose build`는 시간이 더 걸릴 수 있습니다.

## GitHub / ENV_FILE 과의 관계

- 이 웹훅은 **애플리케이션 `.env.production`에 넣지 않아도 됩니다.** (호스트 cron이 읽는 파일만 설정하면 됨.)
- 팀 정책상 레포에 넣지 않고 EC2에만 두는 것을 권장합니다.
