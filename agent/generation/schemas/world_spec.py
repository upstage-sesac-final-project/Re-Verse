"""WorldSpec — 1차 LLM(GameDesigner) 출력 스키마."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PartyMemberSpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    """파티원 한 명."""

    name: str
    role: str  # "warrior", "mage", "healer", "thief", "archer", "default"
    class_name: str  # 직업명 (한글 가능, 예: "전사", "마법사")
    personality: str = ""  # 성격 (1문장)
    gender: str = "male"  # "male" | "female"

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # class_name 대체 필드
        if "class_name" not in data:
            for alt in ("job", "class", "occupation", "profession"):
                if alt in data:
                    data["class_name"] = data[alt]
                    break
            else:
                data.setdefault("class_name", "모험가")
        # role 기본값
        data.setdefault("role", "default")
        return data


class EnemySpec(BaseModel):
    model_config = ConfigDict(extra="ignore")
    """적 한 마리."""

    name: str
    tier: Literal["weak", "normal", "elite", "boss"] = "normal"
    location: str = ""  # 등장 맵 이름

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # tier 대체 필드
        if "tier" not in data:
            for alt in ("rank", "grade", "level", "strength"):
                if alt in data:
                    data["tier"] = data[alt]
                    break
        # tier 값 정규화
        tier = data.get("tier", "normal")
        valid = {"weak", "normal", "elite", "boss"}
        if tier not in valid:
            data["tier"] = "normal"
        return data


class GameMapInfo(BaseModel):
    """맵 고수준 설명."""

    model_config = ConfigDict(extra="ignore")

    name: str
    map_type: Literal["town", "dungeon", "boss", "field"] = "field"
    description: str = ""
    connects_to: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # map_type 대체 필드
        if "map_type" not in data:
            for alt in ("type", "area_type", "zone_type"):
                if alt in data:
                    data["map_type"] = data[alt]
                    break
        # map_type 값 정규화
        mt = data.get("map_type", "field")
        if mt not in {"town", "dungeon", "boss", "field"}:
            data["map_type"] = "field"
        return data


class WorldSpec(BaseModel):
    """1차 LLM(GameDesigner)이 사용자 prompt 한 문장으로 생성하는 전체 게임 설계."""

    model_config = ConfigDict(extra="ignore")

    # 세계관
    game_title: str
    theme: str  # "동화 판타지", "중세 판타지", "SF" 등
    story_synopsis: str  # 전체 줄거리 (2~3문장)
    tone: str = "standard"  # "dark", "lighthearted", "standard"

    # 파티
    party: list[PartyMemberSpec]  # 2~4명

    # 적
    enemies: list[EnemySpec]  # weak 3~5 + normal 2~3 + boss 1

    # 맵
    maps: list[GameMapInfo]  # 3~4개

    # 시스템
    difficulty: Literal["easy", "normal", "hard"] = "normal"
    currency_name: str = "G"
    playtime_minutes: int = 7

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # theme 대체 필드
        if "theme" not in data:
            for alt in ("genre", "setting", "world_theme", "world", "atmosphere"):
                if alt in data:
                    data["theme"] = data[alt]
                    break
            else:
                data["theme"] = "판타지"
        # story_synopsis 대체 필드
        if "story_synopsis" not in data:
            for alt in (
                "synopsis",
                "story",
                "plot",
                "summary",
                "overview",
                "narrative",
                "background",
                "description",
                "story_summary",
            ):
                if alt in data:
                    data["story_synopsis"] = data[alt]
                    break
            else:
                data["story_synopsis"] = (
                    f"{data.get('theme', '판타지')} 세계를 배경으로 한 모험 RPG."
                )
        # enemies: dict {"weak": [...], "normal": [...], ...} → flat list
        enemies = data.get("enemies")
        if isinstance(enemies, dict):
            flat = []
            for tier, members in enemies.items():
                if isinstance(members, list):
                    for e in members:
                        if isinstance(e, dict):
                            e.setdefault("tier", tier)
                            flat.append(e)
            data["enemies"] = flat

        # party: dict → list (혹시 모를 경우)
        party = data.get("party")
        if isinstance(party, dict):
            data["party"] = list(party.values())

        # maps: dict → list
        maps = data.get("maps")
        if isinstance(maps, dict):
            data["maps"] = list(maps.values())

        # difficulty 값 정규화
        diff = data.get("difficulty", "normal")
        if diff not in {"easy", "normal", "hard"}:
            data["difficulty"] = "normal"
        # playtime_minutes: int 변환
        pt = data.get("playtime_minutes", 7)
        if not isinstance(pt, int):
            try:
                data["playtime_minutes"] = int(str(pt).split("~")[0].strip())
            except Exception:
                data["playtime_minutes"] = 7
        return data
