# EC2 전원/상태 변경 알림 (EventBridge -> Lambda -> Discord)

EC2 내부 스크립트(`ec2_host_monitor.sh`)는 인스턴스가 꺼지면 함께 멈춥니다.
그래서 **인스턴스 종료/중지 알림은 AWS 이벤트 기반**으로 구성해야 합니다.

이 문서는 다음 흐름을 설정합니다.

```text
EC2 상태 변경 이벤트 -> EventBridge 규칙 -> Lambda -> Discord 웹훅
```

---

## 1) 준비물

- Discord 웹훅 URL
- 대상 EC2 인스턴스 ID (`i-...`)
- AWS 콘솔 접근 권한 (EventBridge/Lambda/IAM)

---

## 2) Lambda 함수 만들기

### 2-1. 코드 업로드

저장소 파일을 Lambda 코드로 사용:

- `scripts/aws/ec2_state_discord_lambda.py`

핸들러:

- `ec2_state_discord_lambda.lambda_handler`

> 파일 이름을 그대로 올렸다면 핸들러 문자열도 위와 동일합니다.

### 2-2. Lambda 환경 변수

아래를 설정하세요.

- `DISCORD_INFRA_WEBHOOK_URL` (권장, 기존 인프라 알림과 통일)
- `TARGET_INSTANCE_ID` (선택, 특정 인스턴스만 필터링)
- `TIMEZONE=Asia/Seoul` (선택)

참고:

- `DISCORD_INFRA_WEBHOOK_URL`가 없으면 `DISCORD_WEBHOOK_URL`를 fallback으로 사용합니다.

### 2-3. Lambda Timeout

- 기본 3초는 짧을 수 있어 **10초** 권장

### 2-4. Lambda IAM 권한

실행 역할에 다음 권한이 필요합니다.

- `AWSLambdaBasicExecutionRole` (CloudWatch Logs)
- `ec2:DescribeInstances` (EC2 Name tag 조회용)

`ec2:DescribeInstances`가 없으면 인스턴스 이름이 `unknown`으로 표시됩니다.

---

## 3) EventBridge 규칙 만들기

### 3-1. 이벤트 패턴

아래 템플릿 파일을 사용하세요.

- `scripts/aws/eventbridge_ec2_state_pattern.json`

`i-REPLACE_WITH_YOUR_INSTANCE_ID`를 실제 ID로 바꿉니다.

원하는 상태만 선택 가능:

- 다운 감지 위주: `stopping`, `stopped`, `terminated`
- 복구 감지도 필요: `running` 추가

### 3-2. 타겟 연결

EventBridge Rule Target을 위 Lambda로 연결합니다.

---

## 4) 테스트 순서

1. EventBridge 규칙 저장
2. EC2를 `Stop` 실행
3. Discord 알림 수신 확인
4. EC2 `Start` 후 `running` 알림 확인(패턴에 넣은 경우)

---

## 5) 운영 팁

- 운영 서버만 감시하려면 `instance-id` 필터 유지
- 여러 인스턴스를 감시하려면 `instance-id` 배열에 추가
- 알림 스팸이 많으면 `running` 상태를 빼고 다운 이벤트만 유지

---

## 6) 자주 하는 질문

### Q1. 기존 `ec2_host_monitor.sh`는 지워야 하나요?

아니요. 역할이 다릅니다.

- `ec2_host_monitor.sh`: **켜져 있는 서버의 디스크/부하** 감시
- EventBridge/Lambda: **서버가 꺼졌는지(상태 변경)** 감시

둘 다 함께 쓰는 것이 가장 안전합니다.

### Q2. 앱이 죽었는데 EC2는 살아 있으면?

이 구성만으로는 못 잡을 수 있습니다. 아래를 같이 권장합니다.

- CloudWatch Alarm: `StatusCheckFailed`
- 외부 Uptime 체크: `/health` 엔드포인트
