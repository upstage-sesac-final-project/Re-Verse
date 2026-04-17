"""operation_ir subpackage — Definition 노드가 생성하고 planner/validator 가 소비하는 정규화된 수정 명령 IR.

## 구성 모듈

- `types`      — OperationTuple / OperationValue / OperationSubject TypedDict 정의
- `build`      — Step 5 경로: extractions + classifications → operation_tuples (LLM 0 회)
- `normalize`  — Step 6 경로: LLM modifications → operation_tuples (fallback)
- `validate`   — Step 10 경로: degenerate 검증 (subject 미식별 / updates 비어있음)
- `resolve`    — Step 9 경로: GameIndex 기반 subject.id / value.ref 후처리

## 공개 API

    from agent.editor.operation_ir import (
        OperationTuple,
        build_from_extractions,
        normalize_modifications,
        validate_operation_tuples,
        apply_index_resolution,
    )
"""

from agent.editor.operation_ir.build import build_from_extractions
from agent.editor.operation_ir.normalize import normalize_modifications
from agent.editor.operation_ir.resolve import apply_index_resolution
from agent.editor.operation_ir.types import (
    OperationSubject,
    OperationTuple,
    OperationValue,
)
from agent.editor.operation_ir.validate import validate_operation_tuples

__all__ = [
    "OperationSubject",
    "OperationTuple",
    "OperationValue",
    "apply_index_resolution",
    "build_from_extractions",
    "normalize_modifications",
    "validate_operation_tuples",
]
