from fastapi import APIRouter

from app.api.v1 import (
    admin,
    briefs,
    clusters,
    documents,
    entities,
    health,
    sources,
    stream,
    takedown,
    uploads,
)

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(documents.router, tags=["documents"])
api_router.include_router(briefs.router, tags=["briefs"])
api_router.include_router(entities.router, tags=["entities"])
api_router.include_router(stream.router, tags=["stream"])
api_router.include_router(clusters.router, tags=["clusters"])
api_router.include_router(sources.router, tags=["sources"])
api_router.include_router(uploads.router, tags=["uploads"])
api_router.include_router(admin.router, tags=["admin"])
api_router.include_router(takedown.router, tags=["compliance"])
