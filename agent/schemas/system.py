# agent/schemas/system.py

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AudioFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", description="오디오 파일명")
    pan: int = Field(default=0, ge=-100, le=100, description="패닝")
    pitch: int = Field(default=100, ge=50, le=150, description="피치")
    volume: int = Field(default=90, ge=0, le=100, description="볼륨")


class Vehicle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bgm: AudioFile = Field(description="탑승 시 재생되는 BGM")
    characterIndex: int = Field(default=0, ge=0, description="캐릭터 시트 인덱스")
    characterName: str = Field(default="", description="캐릭터 시트 인덱스")
    startMapId: int = Field(default=0, ge=0, description="시작 맵 ID")
    startX: int = Field(default=0, ge=0, description="시작 X 좌표")
    startY: int = Field(default=0, ge=0, description="시작 Y 좌표")


class AttackMotion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: int = Field(default=0, ge=0, description="공격 모션 타입")
    weaponImageId: int = Field(default=0, ge=0, description="무기 이미지 ID")


class TestBattler(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actorId: int = Field(ge=0, description="전투 테스트용 액터 ID")
    equips: list[int] = Field(default_factory=list, description="장비 ID 목록")
    level: int = Field(default=1, ge=1, description="레벨")


class SystemTerms(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basic: list[str | None] = Field(default_factory=list, description="기본 용어 목록")
    commands: list[str | None] = Field(default_factory=list, description="커맨드 용어 목록")
    params: list[str | None] = Field(default_factory=list, description="파라미터 용어 목록")
    messages: dict[str, str] = Field(default_factory=dict, description="시스템 메시지 사전")


class System(BaseModel):
    model_config = ConfigDict(extra="forbid")

    airship: Vehicle = Field(description="비공정 설정")
    armorTypes: list[str | None] = Field(default_factory=list, description="방어구 타입 목록")
    attackMotions: list[AttackMotion | None] = Field(default_factory=list, description="무기 타입별 공격 모션")
    battleBgm: AudioFile = Field(description="전투 BGM")
    battleback1Name: str = Field(default="", description="기본 전투 배경 1")
    battleback2Name: str = Field(default="", description="기본 전투 배경 2")
    battlerHue: int = Field(default=0, description="테스트 적 색조")
    battlerName: str = Field(default="", description="테스트 적 이미지명")
    boat: Vehicle = Field(description="보트 설정")
    currencyUnit: str = Field(default="", description="화폐 단위")
    defeatMe: AudioFile = Field(description="패배 ME")
    editMapId: int = Field(default=0, ge=0, description="에디터 마지막 편집 맵 ID")
    elements: list[str | None] = Field(default_factory=list, description="속성 목록")
    equipTypes: list[str | None] = Field(default_factory=list, description="장비 타입 목록")
    gameTitle: str = Field(default="", description="게임 제목")
    gameoverMe: AudioFile = Field(description="게임오버 ME")
    locale: str = Field(default="", description="로케일")
    magicSkills: list[int] = Field(default_factory=list, description="마법 스킬 타입 ID 목록")
    menuCommands: list[bool] = Field(default_factory=list, description="메뉴 커맨드 표시 여부")
    optDisplayTp: bool = Field(default=False, description="TP 표시 여부")
    optDrawTitle: bool = Field(default=True, description="타이틀 그리기 여부")
    optExtraExp: bool = Field(default=False, description="예비 멤버 경험치 획득 여부")
    optFloorDeath: bool = Field(default=False, description="바닥 데미지로 전투불능 가능 여부")
    optFollowers: bool = Field(default=True, description="팔로워 표시 여부")
    optSideView: bool = Field(default=False, description="사이드뷰 전투 여부")
    optSlipDeath: bool = Field(default=False, description="슬립 데미지로 전투불능 가능 여부")
    optTransparent: bool = Field(default=False, description="시작 시 투명 상태 여부")
    partyMembers: list[int] = Field(default_factory=list, description="초기 파티 액터 ID 목록")
    ship: Vehicle = Field(description="배 설정")
    skillTypes: list[str | None] = Field(default_factory=list, description="스킬 타입 목록")
    sounds: list[AudioFile] = Field(default_factory=list, description="시스템 사운드 목록")
    startMapId: int = Field(default=0, ge=0, description="게임 시작 맵 ID")
    startX: int = Field(default=0, ge=0, description="게임 시작 X 좌표")
    startY: int = Field(default=0, ge=0, description="게임 시작 Y 좌표")
    switches: list[str | None] = Field(default_factory=list, description="스위치명 목록")
    terms: SystemTerms = Field(description="시스템 용어 설정")
    testBattlers: list[TestBattler] = Field(default_factory=list, description="전투 테스트 액터 설정")
    testTroopId: int = Field(default=0, ge=0, description="전투 테스트 적군 ID")
    title1Name: str = Field(default="", description="타이틀 이미지 1")
    title2Name: str = Field(default="", description="타이틀 이미지 2")
    titleBgm: AudioFile = Field(description="타이틀 BGM")
    variables: list[str | None] = Field(default_factory=list, description="변수명 목록")
    versionId: int = Field(default=0, ge=0, description="버전 ID")
    victoryMe: AudioFile = Field(description="승리 ME")
    weaponTypes: list[str | None] = Field(default_factory=list, description="무기 타입 목록")
    windowTone: list[int] = Field(default_factory=list, description="윈도우 톤 [R, G, B, Gray]")

    @model_validator(mode="after")
    def validate_window_tone(self):
        if self.windowTone and len(self.windowTone) != 4:
            raise ValueError("windowTone은 길이 4의 배열이어야 함")
        return self
