# vendor/ (참고용 소스 보관)

이 디렉터리는 **통합 MCP(`RPGMakerMZ_MCP`)에 포함되지 않는** 선택 영역입니다.

## 목적

- MCP 1·2·4 원본을 **읽기 전용**으로 두고 포팅 시 diff·검색하기 위함입니다.
- **빌드 산출물(`dist/`)에는 넣지 않습니다.** (`tsconfig.build.json`에 포함하지 않음)

## 왜 이렇게 나누나

- 네 개 레포를 한 폴더에 **복사만** 하면 의존성·진입점이 여러 개라 “단일 MCP”가 되지 않습니다.
- 실제 통합은 `handlers/` 등으로 **코드를 옮긴 뒤** vendor는 삭제하거나 비워도 됩니다.

## 권장 사용법

1. 필요 시 `git submodule` 또는 수동 복사로 `vendor/mcp1`, `vendor/mcp2` 등에 원본을 둡니다.
2. 포팅이 끝난 툴은 `merger/implementation-status.json`에서 pending → implemented로 반영합니다.
3. 더 이상 참고하지 않으면 vendor를 제거해 레포 크기를 줄입니다.
