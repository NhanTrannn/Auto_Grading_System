from fastapi import APIRouter

from app.api.routes import barem_assistant, barems, grading, health, manage, ocr, pipeline

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(grading.router, prefix="/grading", tags=["grading"])
api_router.include_router(pipeline.router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(manage.router, prefix="/pipeline", tags=["pipeline"])
api_router.include_router(barems.router, prefix="/barems", tags=["barems"])
api_router.include_router(barem_assistant.router, prefix="/barem-assistant", tags=["barems"])
api_router.include_router(ocr.router, prefix="/ocr", tags=["ocr"])
