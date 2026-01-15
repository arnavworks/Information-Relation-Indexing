"""Asynchronous ingestion control-plane endpoints."""

import re
from hashlib import sha256
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

import anyio
from fastapi import APIRouter, Header, HTTPException, UploadFile, status

from iri.api.dependencies import IngestionServiceDependency
from iri.api.schemas import IngestionAccepted, IngestionCreate, IngestionStatusResponse
from iri.core.config import get_settings
from iri.db.models import DataSourceType
from iri.services.ingestion import IdempotencyConflictError, IngestionNotFoundError
from iri.services.ingestion_processor import schedule_ingestion

router = APIRouter(prefix="/ingestions", tags=["ingestions"])


def _source_type(filename: str) -> DataSourceType:
    extension = Path(filename).suffix.casefold()
    if extension == ".pdf":
        return DataSourceType.PDF
    if extension == ".json":
        return DataSourceType.JSON
    if extension in {".csv", ".xls", ".xlsx"}:
        return DataSourceType.SPREADSHEET
    return DataSourceType.DOCUMENT


@router.post("", response_model=IngestionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def create_ingestion(
    request: IngestionCreate,
    service: IngestionServiceDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=255),
    ],
) -> IngestionAccepted:
    """Atomically register a DRI source and place durable extraction work in queue."""

    try:
        return await service.enqueue(request, idempotency_key)
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post("/upload", response_model=IngestionAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_ingestion(
    file: UploadFile,
    service: IngestionServiceDependency,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=255),
    ],
) -> IngestionAccepted:
    """Persist uploaded bytes, register their DRI identity, and start extraction."""

    settings = get_settings()
    filename = Path(file.filename or "uploaded-document").name
    if Path(filename).suffix.casefold() not in {
        ".pdf",
        ".json",
        ".csv",
        ".txt",
        ".md",
    }:
        raise HTTPException(status_code=415, detail="unsupported source type")
    content = await file.read(settings.max_upload_bytes + 1)
    if not content:
        raise HTTPException(status_code=400, detail="uploaded source is empty")
    if len(content) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="uploaded source exceeds configured limit")

    digest = sha256(content).hexdigest()
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", filename)
    settings.upload_directory.mkdir(parents=True, exist_ok=True)
    path = settings.upload_directory / f"{digest}_{safe_name}"
    await anyio.to_thread.run_sync(path.write_bytes, content)
    request = IngestionCreate(
        source_type=_source_type(filename),
        source_uri=f"upload://{quote(filename)}",
        source_name=filename,
        media_type=file.content_type,
        content_sha256=digest,
        byte_size=len(content),
        source_metadata={"stored_path": str(path)},
    )
    try:
        accepted = await service.enqueue(request, idempotency_key)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    schedule_ingestion(accepted.job_id, path)
    return accepted


@router.get("/{job_id}", response_model=IngestionStatusResponse)
async def get_ingestion(
    job_id: UUID,
    service: IngestionServiceDependency,
) -> IngestionStatusResponse:
    try:
        return await service.status(job_id)
    except IngestionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ingestion not found",
        ) from exc
