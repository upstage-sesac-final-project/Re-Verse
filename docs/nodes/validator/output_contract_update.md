# Validator Output Contract Update

## 상태

- 상태: 반영 완료
- 기준 파일: `agent/graph/nodes/validator.py`
- 관련 테스트: `agent/tests/test_validator.py`

## 현재 출력 계약

validator 표준 출력은 아래 필드만 사용한다.

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

실패 시에는 top-level에만 `retry_count`가 추가된다.

## 현재 반영된 변경

1. 출력 조합을 Pydantic 모델로 고정했다.
2. `validator()` 내부는 모델 인스턴스로 처리하고 마지막에만 `model_dump()` 한다.
3. 구형 top-level `validation_result`를 제거했다.
4. item-level `message`, `error_count`를 제거했다.

## 현재 사용 모델

```python
class ValidationErrorItem(BaseModel):
    loc: Any
    msg: str


class FileValidationResult(BaseModel):
    target: str
    success: bool
    errors: list[ValidationErrorItem] = Field(default_factory=list)


class ValidatorOutput(BaseModel):
    validation_results: list[FileValidationResult] = Field(default_factory=list)
    validation_summary: str
    success: bool
    retry_count: int | None = None
```

## 현재 동작 메모

- `model.model_validate(payload, strict=True)`를 사용한다.
- 따라서 `"1"` 같은 문자열 숫자는 더 이상 정수 필드로 자동 변환되어 통과하지 않는다.
- snapshot path 입력과 in-memory payload 입력을 모두 처리한다.

## 남은 확인 포인트

- 숨은 consumer가 여전히 `validation_result`를 참조하는지
- unsupported schema 파일을 더 확장할지
- CLI와 테스트 전용 실행 경로를 분리할지
