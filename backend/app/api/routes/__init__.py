from fastapi import APIRouter

from app.api.routes import grading, health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(grading.router, prefix="/grading", tags=["grading"])
