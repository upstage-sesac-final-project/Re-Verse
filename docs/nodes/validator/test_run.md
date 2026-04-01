# Validator Test Run Guide

## 목적

`agent/tests/test_validator.py`를 CLI처럼 실행해서 특정 JSON 파일만 validator로 검증하는 방법을 정리한다.


## 전제

- 프로젝트 루트에서 실행한다.
- `uv`를 사용할 수 있어야 한다.
- 현재 구조에서는 validator 실행 시 import 과정에서 backend settings도 같이 로드되므로, `JWT_SECRET_KEY`가 필요하다.
- 이 값은 파일 수정 없이 현재 PowerShell 세션에만 임시로 넣어도 된다.
- 현재 validator는 `model_validate(..., strict=True)`를 사용하므로 문자열 숫자 같은 자동 형변환은 통과하지 않는다.


## 1. 세션에 임시 환경변수 넣기

PowerShell에서 한 번만 실행:

```powershell
$env:JWT_SECRET_KEY="test-secret"
```

확인:

```powershell
echo $env:JWT_SECRET_KEY
```

현재 창을 닫으면 값은 사라진다.


## 2. Actors.json만 단독 검증하기

`Actors.json` 한 파일만 보고 싶으면 `--current-dir`를 주지 않는다.

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --modified C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json
```

이 방식은 `modified_game_state`에 `Actors.json`만 넣기 때문에 사실상 단독 검증이다.


## 3. 원본과 수정본을 1:1로 검증하기

원본 파일과 수정본 파일을 각각 지정하려면 `--current`와 `--modified`를 사용한다.

예시:

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --current C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json `
  --modified C:\Users\yebin\Desktop\temp\Actors.json
```

의미:

- `--current`: 기준이 되는 원본 파일
- `--modified`: 실제 검증할 수정본 파일


## 4. `--current-dir`를 쓰면 안 되는 경우

`--current-dir`를 주면 해당 폴더의 모든 `.json` 파일이 `current_game_state`에 들어간다.

예를 들어 아래 명령은:

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --current-dir C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data `
  --modified C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json
```

실질적으로 `game_002\data` 폴더 전체 검증처럼 동작한다.  
`Actors.json`만 보고 싶다면 `--current-dir`는 사용하지 않는다.


## 5. `data` 안의 모든 JSON 파일을 한 번에 검증하기

현재 스크립트는 `--modified`에 **폴더 경로**를 직접 받을 수 없다.  
`--modified`는 파일 경로만 받으며, 내부에서 `is_file()` 검사도 한다.

즉 아래처럼는 동작하지 않는다.

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --modified C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data
```

현재 구현 기준으로 `data` 폴더 안의 모든 JSON 파일을 한 번에 검증하려면 다음처럼 실행한다.

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --current-dir C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data `
  --modified C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json
```

이 명령이 전체 검증처럼 동작하는 이유:

- `--current-dir`가 `data` 폴더의 모든 `.json`을 `current_game_state`로 읽음
- `--modified`로 준 파일이 `modified_game_state`를 만들 때 current 위에 merge됨
- 현재 validator는 최종 `modified_game_state`에 들어 있는 파일들을 모두 검증함

즉, `--modified`에 아무 JSON 파일 하나만 넣어도 결과적으로 `data` 폴더 전체 검증이 된다.

주의:

- 이건 현재 스크립트 구현을 이용한 방식이다.
- 의미상으로는 “폴더 전체 검증 전용 옵션”이 있는 것은 아니다.
- 정말 명시적으로 폴더를 바로 넣고 싶다면 별도 CLI 옵션이 추가되어야 한다.


## 6. 결과 해석

출력은 JSON이며 현재 validator 표준 shape는 아래와 같다.

```json
{
  "validation_results": [
    {
      "target": "Actors.json",
      "success": true,
      "errors": []
    }
  ],
  "validation_summary": "총 1개 파일이 모두 스키마 검증을 통과했습니다.",
  "success": true
}
```

실패 시에는 top-level에 `retry_count`가 추가된다.


## 7. 종료 코드

- `success: true`면 종료 코드 `0`
- `success: false`면 종료 코드 `1`

즉, 명령이 끝났다고 해서 항상 실행 오류는 아니고, validator 결과가 실패여도 종료 코드는 `1`이다.


## 8. 자주 쓰는 명령

현재 세션에 임시 환경변수 설정:

```powershell
$env:JWT_SECRET_KEY="test-secret"
```

`Actors.json`만 단독 검증:

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --modified C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json
```

원본/수정본 1:1 검증:

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --current C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json `
  --modified C:\Users\yebin\Desktop\temp\Actors.json
```

`data` 폴더 전체 검증:

```powershell
uv run --extra dev python agent\tests\test_validator.py `
  --current-dir C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data `
  --modified C:\Users\yebin\Desktop\Re-Verse\storage\games\game_002\data\Actors.json
```

세션에서 환경변수 제거:

```powershell
Remove-Item Env:JWT_SECRET_KEY
```
