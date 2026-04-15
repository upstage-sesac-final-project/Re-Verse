"""공지사항 & 패치노트 엔드포인트.

공개 읽기 + 관리자 전용 쓰기.
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.core.security import get_admin_user
from app.backend.db.session import get_db
from app.backend.models.notice import Announcement, PatchNote
from app.backend.schemas.notice import (
    AnnouncementCreate,
    AnnouncementResponse,
    AnnouncementUpdate,
    LatestVersionResponse,
    PatchNoteCreate,
    PatchNoteResponse,
    PatchNoteUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ── 공개: 공지사항 ────────────────────────────────────


@router.get("/announcements", response_model=list[AnnouncementResponse])
async def list_announcements(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Announcement)
        .where(Announcement.is_published.is_(True))
        .order_by(Announcement.pinned.desc(), Announcement.date.desc())
    )
    return result.scalars().all()


# ── 공개: 패치노트 ────────────────────────────────────


@router.get("/patch-notes", response_model=list[PatchNoteResponse])
async def list_patch_notes(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PatchNote).where(PatchNote.is_published.is_(True)).order_by(PatchNote.date.desc())
    )
    return result.scalars().all()


@router.get("/latest-version", response_model=LatestVersionResponse)
async def get_latest_version(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PatchNote.version)
        .where(PatchNote.is_published.is_(True))
        .order_by(PatchNote.date.desc())
        .limit(1)
    )
    version = result.scalar_one_or_none()
    return LatestVersionResponse(version=version)


# ── 관리자: 공지사항 CRUD ─────────────────────────────


@router.post("/announcements", response_model=AnnouncementResponse, status_code=201)
async def create_announcement(
    data: AnnouncementCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    item = Announcement(
        title=data.title,
        content=data.content,
        date=data.date,
        pinned=data.pinned,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info("[Notices] 공지 생성 | id=%d, title=%s", item.id, item.title)
    return item


@router.put("/announcements/{item_id}", response_model=AnnouncementResponse)
async def update_announcement(
    item_id: int,
    data: AnnouncementUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    item = await db.get(Announcement, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="공지사항을 찾을 수 없습니다."
        )
    for key, val in data.model_dump(exclude_unset=True).items():
        setattr(item, key, val)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/announcements/{item_id}", status_code=204)
async def delete_announcement(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    item = await db.get(Announcement, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="공지사항을 찾을 수 없습니다."
        )
    await db.delete(item)
    await db.commit()


# ── 관리자: 패치노트 CRUD ─────────────────────────────


@router.post("/patch-notes", response_model=PatchNoteResponse, status_code=201)
async def create_patch_note(
    data: PatchNoteCreate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    item = PatchNote(
        version=data.version,
        title=data.title,
        date=data.date,
        changes=json.dumps([c.model_dump() for c in data.changes], ensure_ascii=False),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    logger.info("[Notices] 패치노트 생성 | id=%d, version=%s", item.id, item.version)
    return item


@router.put("/patch-notes/{item_id}", response_model=PatchNoteResponse)
async def update_patch_note(
    item_id: int,
    data: PatchNoteUpdate,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    item = await db.get(PatchNote, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="패치노트를 찾을 수 없습니다."
        )
    updates = data.model_dump(exclude_unset=True)
    if "changes" in updates and updates["changes"] is not None:
        updates["changes"] = json.dumps(
            [c if isinstance(c, dict) else c.model_dump() for c in updates["changes"]],
            ensure_ascii=False,
        )
    for key, val in updates.items():
        setattr(item, key, val)
    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/patch-notes/{item_id}", status_code=204)
async def delete_patch_note(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    item = await db.get(PatchNote, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="패치노트를 찾을 수 없습니다."
        )
    await db.delete(item)
    await db.commit()


# ── 관리자: 전체 목록 (비공개 포함) ───────────────────


@router.get("/admin/announcements", response_model=list[AnnouncementResponse])
async def admin_list_announcements(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    result = await db.execute(select(Announcement).order_by(Announcement.date.desc()))
    return result.scalars().all()


@router.get("/admin/patch-notes", response_model=list[PatchNoteResponse])
async def admin_list_patch_notes(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(get_admin_user),
):
    result = await db.execute(select(PatchNote).order_by(PatchNote.date.desc()))
    return result.scalars().all()
