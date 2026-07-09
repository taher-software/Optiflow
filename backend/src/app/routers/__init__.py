from fastapi import APIRouter

from .registration.router import router as registration_router

api_router = APIRouter()
api_router.include_router(registration_router)

__all__ = ["api_router"]
