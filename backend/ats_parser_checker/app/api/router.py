from fastapi import APIRouter

from app.api.endpoints.feedback import router as feedback_router
from app.api.endpoints.health import router as health_router
from app.api.endpoints.ingestion import router as ingestion_router

api_router = APIRouter(prefix="/api")
api_router.include_router(health_router)
api_router.include_router(ingestion_router)
api_router.include_router(feedback_router)
