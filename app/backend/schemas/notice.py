"""공지사항 & 패치노트 스키마."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── 공지사항 ──────────────────────────────────────────


class AnnouncementCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    date: str = Field(..., min_length=1)
    pinned: bool = False


class AnnouncementUpdate(BaseModel):
    title: str | None = Field(None, max_length=200)
    content: str | None = None
    date: str | None = None
    pinned: bool | None = None
    is_published: bool | None = None


class AnnouncementResponse(BaseModel):
    id: int
    title: str
    content: str
    date: str
    pinned: bool
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ── 패치노트 ──────────────────────────────────────────


class PatchNoteChange(BaseModel):
    type: str  # 'new' | 'fix' | 'improve' | 'remove'
    text: str


class PatchNoteCreate(BaseModel):
    version: str = Field(..., min_length=1, max_length=20)
    title: str = Field(..., min_length=1, max_length=200)
    date: str = Field(..., min_length=1)
    changes: list[PatchNoteChange]


class PatchNoteUpdate(BaseModel):
    version: str | None = Field(None, max_length=20)
    title: str | None = Field(None, max_length=200)
    date: str | None = None
    changes: list[PatchNoteChange] | None = None
    is_published: bool | None = None


class PatchNoteResponse(BaseModel):
    id: int
    version: str
    title: str
    date: str
    changes: list[PatchNoteChange]
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("changes", mode="before")
    @classmethod
    def parse_changes_json(cls, v: str | list) -> list:
        if isinstance(v, str):
            return json.loads(v)
        return v


class LatestVersionResponse(BaseModel):
    version: str | None
