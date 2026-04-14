"""RPG Maker MZ JSON 파일 CRUD — 단일 진입점.

대상 (DB 배열 파일): Actors / Classes / Skills / Items / Weapons / Armors / Enemies / States
단일 객체 파일: System.json

범위 밖: Map 파일, 이벤트 커맨드, 플러그인

설계 원칙:
- 정제된 입력 → JSON 파일 수정.  step 문맥 해석은 executor 책임.
- 모든 메서드는 동기(sync).
- 반환값은 executor 의 changes_log 호환 포맷:
    {
        "success": bool,
        "data": dict | list | None,   # 엔티티 or 결과 데이터
        "modified_files": list[str],  # mutation=[file], query=[]
        "error": str | None,
        "exists": bool | None,        # query 전용
        "entity_id": int | None,      # create/get 후 확정된 id
    }
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from agent.tools.entity_templates import build_template

logger = logging.getLogger(__name__)

# System.json 이 아닌 "배열형" DB 파일 집합
_DB_ARRAY_FILES = frozenset(
    {
        "Actors.json",
        "Classes.json",
        "Skills.json",
        "Items.json",
        "Weapons.json",
        "Armors.json",
        "Enemies.json",
        "States.json",
    }
)


def _ok(data: Any, modified_files: list[str], *, entity_id: int | None = None) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "modified_files": modified_files,
        "error": None,
        "entity_id": entity_id,
    }


def _ok_query(
    data: Any,
    *,
    exists: bool,
    entity_id: int | None = None,
) -> dict[str, Any]:
    return {
        "success": True,
        "data": data,
        "modified_files": [],
        "error": None,
        "exists": exists,
        "entity_id": entity_id,
    }


def _fail(error: str) -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "modified_files": [],
        "error": error,
        "entity_id": None,
    }


class RPGMakerCRUD:
    """RPG Maker MZ JSON 파일 CRUD 단일 진입점."""

    def __init__(self, data_path: Path) -> None:
        self._data_path = data_path

    # ──────────────────────────────────────────────
    # private 유틸
    # ──────────────────────────────────────────────

    def _load(self, file: str) -> Any:
        """JSON 파일 로드. 실패 시 예외 전파."""
        fp = self._data_path / file
        return json.loads(fp.read_text(encoding="utf-8"))

    def _save(self, file: str, data: Any) -> None:
        """JSON 파일 저장. ensure_ascii=False, indent=None."""
        fp = self._data_path / file
        fp.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def _find_by_id(self, data: list, entity_id: int) -> dict | None:
        """배열에서 id 로 엔티티 dict 반환. 없으면 None."""
        if entity_id < 0 or entity_id >= len(data):
            return None
        entry = data[entity_id]
        return entry if isinstance(entry, dict) else None

    def _find_by_name(self, data: list, name: str) -> dict | None:
        """배열에서 name 필드 완전 일치(대소문자 무시)로 첫 번째 엔티티 반환."""
        t = name.strip().lower()
        for entry in data:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("name") or "").strip().lower() == t:
                return entry
        return None

    def _find_index_by_name(self, data: list, name: str) -> int | None:
        """name 완전 일치로 인덱스(=id) 반환. 없으면 None."""
        t = name.strip().lower()
        for i, entry in enumerate(data):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("name") or "").strip().lower() == t:
                return i
        return None

    def _next_id(self, data: list) -> int:
        """null 슬롯(index ≥ 1) 우선 탐색. 없으면 append 위치(=len(data))."""
        for i in range(1, len(data)):
            if data[i] is None:
                return i
        return len(data)

    # ──────────────────────────────────────────────
    # DB 배열 파일 공개 메서드
    # ──────────────────────────────────────────────

    def get(
        self,
        file: str,
        entity_id: int | None = None,
        name: str | None = None,
    ) -> dict[str, Any]:
        """단건 조회. entity_id 우선, 없으면 name 완전 일치.

        Returns changes_log 호환 포맷.
        """
        try:
            data = self._load(file)
        except Exception as e:
            return _fail(f"{file} 로드 실패: {e}")

        if not isinstance(data, list):
            return _fail(f"{file} 는 배열 형식이 아닙니다")

        entry: dict | None = None
        resolved_id: int | None = None

        if entity_id is not None:
            entry = self._find_by_id(data, entity_id)
            resolved_id = entity_id if entry else None
        elif name:
            entry = self._find_by_name(data, name)
            if entry:
                resolved_id = entry.get("id")

        exists = entry is not None
        return _ok_query(entry, exists=exists, entity_id=resolved_id)

    def search(self, file: str, term: str) -> dict[str, Any]:
        """name 필드 부분 문자열 매칭(대소문자 무시). 일치 엔티티 리스트 반환."""
        try:
            data = self._load(file)
        except Exception as e:
            return _fail(f"{file} 로드 실패: {e}")

        if not isinstance(data, list):
            return _fail(f"{file} 는 배열 형식이 아닙니다")

        t = (term or "").strip().lower()
        results: list[dict] = []
        first_id: int | None = None

        for entry in data:
            if not isinstance(entry, dict):
                continue
            nm = str(entry.get("name") or "").strip().lower()
            if not nm:
                continue
            if t and t not in nm:
                continue
            results.append(entry)
            if first_id is None:
                first_id = entry.get("id")

        exists = len(results) > 0
        result = _ok_query(results, exists=exists, entity_id=first_id)
        return result

    def create(self, file: str, fields: dict[str, Any], action: str = "create") -> dict[str, Any]:
        """새 엔티티 생성 후 저장.

        template merge: DEFAULT_TEMPLATES[file] → SKILL_PRESETS[action](skill만) → fields
        id / name 은 이 메서드에서 확정한다.
        """
        # name 필드 정규화
        norm_fields: dict[str, Any] = dict(fields)
        if "name" not in norm_fields:
            for alt in ("skill_name", "actor_name", "item_name", "enemy_name", "class_name"):
                if alt in norm_fields:
                    norm_fields["name"] = norm_fields.pop(alt)
                    break

        name = str(norm_fields.get("name") or "").strip()
        if not name:
            return _fail(f"{file} create: name 필드가 필요합니다")

        try:
            template = build_template(file, action, norm_fields)
        except ValueError as e:
            return _fail(str(e))

        try:
            data = self._load(file)
        except Exception as e:
            return _fail(f"{file} 로드 실패: {e}")

        if not isinstance(data, list):
            return _fail(f"{file} 는 배열 형식이 아닙니다")

        new_id = self._next_id(data)
        template["id"] = new_id
        template["name"] = name

        if new_id < len(data):
            data[new_id] = template
        else:
            data.append(template)

        try:
            self._save(file, data)
        except Exception as e:
            return _fail(f"{file} 저장 실패: {e}")

        logger.info("[CRUD] create %s id=%d name=%s", file, new_id, name)
        return _ok(template, [file], entity_id=new_id)

    def update(self, file: str, entity_id: int, updates: dict[str, Any]) -> dict[str, Any]:
        """단건 update. updates dict 를 기존 엔티티에 key 단위 merge.

        damage / effects 같은 중첩 필드는 통째 교체 (부분 merge 없음).
        """
        try:
            data = self._load(file)
        except Exception as e:
            return _fail(f"{file} 로드 실패: {e}")

        if not isinstance(data, list):
            return _fail(f"{file} 는 배열 형식이 아닙니다")

        entry = self._find_by_id(data, entity_id)
        if entry is None:
            return _fail(f"{file}: id={entity_id} 엔티티를 찾을 수 없습니다")

        for k, v in updates.items():
            entry[k] = v

        try:
            self._save(file, data)
        except Exception as e:
            return _fail(f"{file} 저장 실패: {e}")

        logger.info("[CRUD] update %s id=%d keys=%s", file, entity_id, sorted(updates.keys()))
        return _ok(entry, [file], entity_id=entity_id)

    def update_all(self, file: str, updates: dict[str, Any]) -> dict[str, Any]:
        """배열의 모든 non-null 엔티티에 updates 를 적용한다 (bulk update).

        damage / effects 는 통째 교체.
        """
        try:
            data = self._load(file)
        except Exception as e:
            return _fail(f"{file} 로드 실패: {e}")

        if not isinstance(data, list):
            return _fail(f"{file} 는 배열 형식이 아닙니다")

        updated_ids: list[int] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            for k, v in updates.items():
                entry[k] = v
            eid = entry.get("id")
            if eid is not None:
                updated_ids.append(int(eid))

        if not updated_ids:
            return _fail(f"{file}: 업데이트 대상 엔티티가 없습니다")

        try:
            self._save(file, data)
        except Exception as e:
            return _fail(f"{file} 저장 실패: {e}")

        logger.info(
            "[CRUD] update_all %s count=%d keys=%s", file, len(updated_ids), sorted(updates.keys())
        )
        return _ok({"updated_ids": updated_ids}, [file])

    def delete(self, file: str, entity_id: int) -> dict[str, Any]:
        """엔티티를 null 로 교체 (RPG Maker MZ 배열 인덱스 보존 방식)."""
        try:
            data = self._load(file)
        except Exception as e:
            return _fail(f"{file} 로드 실패: {e}")

        if not isinstance(data, list):
            return _fail(f"{file} 는 배열 형식이 아닙니다")

        entry = self._find_by_id(data, entity_id)
        if entry is None:
            return _fail(f"{file}: id={entity_id} 엔티티를 찾을 수 없습니다")

        data[entity_id] = None

        try:
            self._save(file, data)
        except Exception as e:
            return _fail(f"{file} 저장 실패: {e}")

        logger.info("[CRUD] delete %s id=%d", file, entity_id)
        return _ok({"deleted_id": entity_id}, [file])

    # ──────────────────────────────────────────────
    # System.json 전용
    # ──────────────────────────────────────────────

    def get_system(self) -> dict[str, Any]:
        """System.json 전체 반환."""
        try:
            data = self._load("System.json")
        except Exception as e:
            return _fail(f"System.json 로드 실패: {e}")
        return _ok_query(data, exists=True)

    def update_system_field(self, key_path: str, value: Any) -> dict[str, Any]:
        """System.json 특정 필드 업데이트.

        key_path 형식:
          - "gameTitle"          → data["gameTitle"] = value
          - "variables.1"        → data["variables"][1] = value
          - "switches.3"         → data["switches"][3] = value
          - "startMapId"         → data["startMapId"] = value
        """
        try:
            data = self._load("System.json")
        except Exception as e:
            return _fail(f"System.json 로드 실패: {e}")

        if not isinstance(data, dict):
            return _fail("System.json 는 dict 형식이어야 합니다")

        parts = key_path.split(".", 1)
        top_key = parts[0]

        if len(parts) == 2:
            # 배열 인덱스 접근 (예: variables.1)
            sub = parts[1]
            try:
                idx = int(sub)
            except ValueError:
                return _fail(f"key_path '{key_path}' 의 인덱스 '{sub}' 가 정수가 아닙니다")
            target_arr = data.get(top_key)
            if not isinstance(target_arr, list):
                return _fail(f"System.json['{top_key}'] 가 배열이 아닙니다")
            if idx < 0 or idx >= len(target_arr):
                return _fail(f"System.json['{top_key}'][{idx}] 범위 초과 (len={len(target_arr)})")
            target_arr[idx] = value
        else:
            data[top_key] = value

        try:
            self._save("System.json", data)
        except Exception as e:
            return _fail(f"System.json 저장 실패: {e}")

        logger.info("[CRUD] update_system_field key_path=%s", key_path)
        return _ok({"key_path": key_path, "value": value}, ["System.json"])

    def update_starting_position(
        self,
        map_id: int | None = None,
        x: int | None = None,
        y: int | None = None,
    ) -> dict[str, Any]:
        """System.json 시작 위치(startMapId / startX / startY) 업데이트."""
        try:
            data = self._load("System.json")
        except Exception as e:
            return _fail(f"System.json 로드 실패: {e}")

        if not isinstance(data, dict):
            return _fail("System.json 는 dict 형식이어야 합니다")

        changed = False
        if map_id is not None:
            data["startMapId"] = int(map_id)
            changed = True
        if x is not None:
            data["startX"] = int(x)
            changed = True
        if y is not None:
            data["startY"] = int(y)
            changed = True

        if not changed:
            return _fail("update_starting_position: mapId / x / y 중 하나 이상 필요합니다")

        try:
            self._save("System.json", data)
        except Exception as e:
            return _fail(f"System.json 저장 실패: {e}")

        logger.info("[CRUD] update_starting_position mapId=%s x=%s y=%s", map_id, x, y)
        return _ok(
            {
                "startMapId": data.get("startMapId"),
                "startX": data.get("startX"),
                "startY": data.get("startY"),
            },
            ["System.json"],
        )
