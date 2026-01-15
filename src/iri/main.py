"""Information Relation Index (IRI) — ASGI application entry point."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from iri import __version__
from iri.api.dependencies import get_embedding_provider
from iri.api.routes import graph, health, ingestions, retrieval
from iri.core.config import get_settings
from iri.core.logging import configure_logging
from iri.db.session import engine
from iri.graph.gateway import configure_graph


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    configure_graph(settings)
    yield
    await get_embedding_provider().aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="Information Relation Index (IRI)",
        summary="Deterministic, concept-first enterprise retrieval with full provenance",
        version=__version__,
        lifespan=lifespan,
    )
    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST"],
            allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        )
    application.include_router(health.router)
    application.include_router(ingestions.router, prefix=settings.api_prefix)
    application.include_router(retrieval.router, prefix=settings.api_prefix)
    application.include_router(graph.router, prefix=settings.api_prefix)
    return application


app = create_app()


def run() -> None:
    uvicorn.run("iri.main:app", host="0.0.0.0", port=8000)
