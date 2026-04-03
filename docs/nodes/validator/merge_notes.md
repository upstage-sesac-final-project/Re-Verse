# Validator Merge Notes

## 상태

- 상태: 병합 방향 논의 완료
- 현재 결과: `validator.py` 기준으로 구조 단순화와 snapshot path 지원이 함께 반영된 상태다.

## 당시 문제

과거에는 두 방향이 충돌했다.

- 단순한 구조를 가진 구형 validator
- executor 계약에 맞는 snapshot path 처리 로직

단순히 구형 파일로 되돌리면 executor와 맞지 않았고, 최신 파일을 그대로 유지하면 병합 흔적과 중복이 많았다.

## 현재 정리 결과

현재 validator는 아래 방향으로 정리된 상태다.

- 기준 파일은 `agent/graph/nodes/validator.py`
- snapshot path와 in-memory payload를 모두 처리
- 출력 계약은 Pydantic 모델 기반으로 단순화
- 성공 여부와 retry_count는 코드가 deterministic하게 결정

## 현재 남아 있는 한계

- schema map에 없는 파일은 unsupported schema로 처리된다.
- `detect_modified_files()`를 계산하지만 실제 검증은 `modified_game_state` 전체를 순회한다.
- validator CLI는 아직 테스트 파일에 붙어 있어 import 경로상 backend settings 영향을 받는다.

## 관련 문서

- 출력 계약: [./output_contract_update.md](./output_contract_update.md)
- 실행 방법: [./test_run.md](./test_run.md)
- 로그 계획: [./log_plan.md](./log_plan.md)
