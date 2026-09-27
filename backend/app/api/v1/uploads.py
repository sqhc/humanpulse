"""开发者手动上传：文件与纯文本两条入口。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminDep
from app.config import get_settings
from app.db import get_session
from app.models.document import Document
from app.models.ops import ManualUpload
from app.pipeline import normalize, simhash
from app.schemas.content import UploadResultOut

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".html", ".htm", ".csv", ".json"}


class ManualTextIn(BaseModel):
    title: str = Field(min_length=3, max_length=512)
    text: str = Field(min_length=40, max_length=200_000)
    url: str | None = Field(default=None, max_length=2048)
    note: str | None = Field(default=None, max_length=500)
    rights_confirmed: bool = Field(description="确认拥有该材料的收录权利")


def _store(filename_suffix: str, payload: bytes) -> Path:
    target_dir = Path(get_settings().uploads_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{uuid.uuid4().hex}{filename_suffix}"
    path.write_bytes(payload)
    return path


async def _create_document(
    session: AsyncSession,
    *,
    filename: str,
    content: str,
    source_url: str | None,
    note: str | None,
    uploader: str | None,
    stored_path: str,
    mime: str | None,
) -> UploadResultOut:
    title = normalize.strip_html(filename if filename else content[:80])
    excerpt = normalize.excerpt_of(content)
    canonical = normalize.canonicalize_url(source_url or "") or f"upload://{uuid.uuid4().hex}"

    upload = ManualUpload(
        filename=filename[:512],
        mime=mime,
        stored_path=stored_path,
        uploader=uploader,
        note=note,
        status="stored",
    )
    session.add(upload)
    await session.flush()

    document = Document(
        source_id=None,
        fetch_run_id=None,
        url=(source_url or canonical)[:2048],
        canonical_url=canonical,
        title=title[:512] or "手动上传材料",
        language=normalize.detect_language(content),
        kind="manual",
        excerpt=excerpt or None,
        content_hash=normalize.content_hash(title, excerpt),
        simhash=simhash.to_signed64(simhash.simhash64(f"{title} {excerpt}")),
        status="pending",
    )
    session.add(document)
    await session.flush()

    upload.document_id = document.id
    await session.flush()
    return UploadResultOut(upload_id=upload.id, document_id=document.id, status=document.status)


@router.post("/uploads", response_model=UploadResultOut, summary="上传文本类材料（管理员）")
async def upload_file(
    session: SessionDep,
    _admin: AdminDep,
    file: Annotated[UploadFile, File(description="txt / md / html / csv / json")],
    title: Annotated[str | None, Form()] = None,
    note: Annotated[str | None, Form()] = None,
    source_url: Annotated[str | None, Form()] = None,
    rights_confirmed: Annotated[bool, Form()] = False,
) -> UploadResultOut:
    if not rights_confirmed:
        raise HTTPException(status_code=422, detail="必须确认拥有该材料的收录权利")
    settings = get_settings()
    suffix = Path(file.filename or "").suffix.lower()
    if suffix and suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=(
                "Phase 1 只支持文本类材料"
                f"（{', '.join(sorted(ALLOWED_SUFFIXES))}）；PDF/Word 计划在 Phase 2 支持"
            ),
        )
    payload = await file.read()
    if len(payload) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"文件超过 {settings.max_upload_mb} MB 限制")

    text = payload.decode("utf-8", errors="replace")
    stored = _store(suffix or ".txt", payload)
    return await _create_document(
        session,
        filename=file.filename or stored.name,
        content=text,
        source_url=source_url,
        note=note,
        uploader="admin",
        stored_path=str(stored),
        mime=file.content_type,
    )


@router.post("/uploads/text", response_model=UploadResultOut, summary="粘贴文本入库（管理员）")
async def upload_text(
    payload: ManualTextIn,
    session: SessionDep,
    _admin: AdminDep,
) -> UploadResultOut:
    if not payload.rights_confirmed:
        raise HTTPException(status_code=422, detail="必须确认拥有该材料的收录权利")
    stored = _store(".txt", payload.text.encode("utf-8"))
    return await _create_document(
        session,
        filename=payload.title,
        content=payload.text,
        source_url=payload.url,
        note=payload.note,
        uploader="admin",
        stored_path=str(stored),
        mime="text/plain",
    )
