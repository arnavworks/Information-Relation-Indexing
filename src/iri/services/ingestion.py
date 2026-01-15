"""Transactional DRI registration and durable ingestion queue creation."""

import json
from hashlib import sha256
from uuid import UUID, uuid4

from iri.api.schemas import IngestionAccepted, IngestionCreate, IngestionStatusResponse
from iri.db.models import DataReference, IngestionJob
from iri.repositories.postgres import IngestionRepository


class IngestionNotFoundError(LookupError):
    pass


class IdempotencyConflictError(ValueError):
    pass


class IngestionService:
    def __init__(self, repository: IngestionRepository) -> None:
        self._repository = repository

    async def enqueue(self, request: IngestionCreate, idempotency_key: str) -> IngestionAccepted:
        canonical_request = json.dumps(
            request.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        request_fingerprint = sha256(canonical_request.encode()).hexdigest()
        existing = await self._repository.find_job_by_idempotency_key(idempotency_key)
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise IdempotencyConflictError(
                    "Idempotency-Key was already used for a different ingestion request"
                )
            return IngestionAccepted(
                job_id=existing.id,
                dri_id=existing.dri_id,
                dri_code=f"DRI{existing.dri_id}",
                status=existing.status,
                reused=True,
            )

        reference = DataReference(**request.model_dump())
        # dri_id is replaced after the reference INSERT is flushed in one transaction.
        proposed_job_id = uuid4()
        job = IngestionJob(
            id=proposed_job_id,
            dri_id=0,
            idempotency_key=idempotency_key,
            request_fingerprint=request_fingerprint,
        )
        reference, job = await self._repository.add_reference_and_job(reference, job)
        if job.request_fingerprint != request_fingerprint:
            raise IdempotencyConflictError(
                "Idempotency-Key was concurrently used for a different ingestion request"
            )
        if reference.id is None:
            raise RuntimeError("DRI identifier missing after registration")
        return IngestionAccepted(
            job_id=job.id,
            dri_id=reference.id,
            dri_code=reference.reference_code,
            status=job.status,
            reused=job.id != proposed_job_id,
        )

    async def status(self, job_id: UUID) -> IngestionStatusResponse:
        job = await self._repository.get_job(job_id)
        if job is None:
            raise IngestionNotFoundError(str(job_id))
        return IngestionStatusResponse(
            job_id=job.id,
            dri_id=job.dri_id,
            dri_code=f"DRI{job.dri_id}",
            status=job.status,
            error_code=job.error_code,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
        )
