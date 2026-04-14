# 추가 기능 로드맵

본 문서는, 유저로부터 요구가 있던 추가 기능에 대해서, 우선도와 실장 방침을 정리한 것입니다.

## 優先度: 高

### Undo / 롤백 메커니즘
- **개요**: JSON 쓰기 시스템 툴 실행 전에 `data/` 디렉토리의 대상 파일을 백업해, 직전의 상태에 되돌릴 수 있도록 한다.
- **初期実装案**:
  - 핸들러 레이어에 `withBackup(projectPath, files, action)` 헬퍼를 추가하고 `fs.copyFile` 로 `.bak` 를 저장.
  - CLI 도구`undo_last_change`를 준비하고 최신 백업을 복원.
  - 장기적으로는 저널 형식으로 여러 단계의 되감기에 대응.

## 優先度: 中

### validate_project 도구
- **개요**: 프로젝트 전체의 일관성 검사(`validateProjectPath`, `checkAssetsIntegrity`, 주요 JSON의 JSON Schema 검증)를 일괄로 실행.
- **初期実装案**:
  - 새로운 핸들러 `handlers/projectValidation.js`를 추가하고 개별 체크를 Promise.all에서 병렬 실행.
  - 결과를 카테고리별로 보고서(ERROR/WARNING/INFO).

### 일괄 처리 도구
- **개요**: 여러 MCP 도구 호출을 하나의 요청으로 함께 실행합니다.
- **初期実装案**:
  - `batch_execute` 도구를 추가하고 `[{ name: string, args: object }]` 의 배열을 순서대로 실행.
  - 도중에 실패했을 경우는 그 이후를 중단해, 성공/실패의 리포트를 돌려준다.

## 優先度: 低

### WebSocket 通知
- **개요**: MCP 서버에서 편집기/클라이언트로 실시간으로 로그 및 진행을 스트리밍.
- **初期実装案**:
  - `ws` 모듈을 사용하여 로컬 WebSocket 서버를 시작하고`Logger`와 함께 작동합니다.
  - `playtest` 와 `batch_execute` 등 장시간 처리 상태 갱신을 송신.

---

각 기능의 상세 설계 및 태스크 분해는 GitHub Issues에서 관리 예정. 우선순위에 따라 순차 구현을 진행한다.
