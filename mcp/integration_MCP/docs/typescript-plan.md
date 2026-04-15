# TypeScript Migration Plan

이 프로젝트를 단계적으로 TypeScript로 마이그레이션하기위한 계획서.

## 0 단계 : 유형 점검 인프라 정비 (완료)
- `tsconfig.json`의 정비 (`allowJs` +`strict`)
- `npm run typecheck`로`tsc --noEmit`를 실행하여 기존 JS 코드의 유형 검사를 가능하게했습니다.

## 1단계: 유형 정보 확장(완료)
- `types/index.d.ts`를 유지 관리하고 주요 데이터 구조 유형을 제공
- `JSDoc` 코멘트를 추가하고 TypeScript로 형식 추론을 강화
- `tsc`오류 0을 필수 조건으로 CI에`npm run typecheck` 추가

## 2단계: 유틸리티 계층 TypeScript화(완료)
- 대상: `utils/` 디렉토리
- 完了内容:
  1. `utils/validation.js` → `utils/validation.ts`로 마이그레이션
  2. `utils/mapHelpers.js` → `utils/mapHelpers.ts`로 마이그레이션
  3. 형식 정의 파일(`.d.ts`) 추가
  4. `npm run build:utils` 스크립트 추가

## 3단계: 핸들러 계층/진입점 TypeScript화(완료)
- 対象: `handlers/`, `index.js`, `toolSchemas.js`
- 完了内容:
  1. 모든 handlers(`project.ts`, `database.ts`, `plugins.ts`, `map.ts`, `events.ts`, `playtest.ts`)를 TypeScript화
  2. `index.js` → `index.ts`로 이동
  3. `toolSchemas.js` → `toolSchemas.ts`로 마이그레이션
  4. `tsconfig.handlers.json`을 준비하고 handlers 용 빌드 설정 추가
  5. Node.js 용 ESM 구성 (`type : "module"`) 유지

## 4단계: CI/CD에 통합(완료)
- GitHub Actions에 'npm run typecheck'를 추가하여 PR에서 유형 오류를 감지합니다.
- 유형 검사가 CI 파이프라인에 통합되어 자동으로 실행됨
- 앞으로는 `npm run build`를 실행하고`dist /` 아티팩트를 패키징 (미 구현)

## 補足
- 단계적 전환을 최우선으로 하고 항상 동작하는 상태를 담보
- JSDoc +`tsc --checkJs true`의 병용도 검토
