from fastapi import APIRouter

from src.app.routers.auth import router as auth_router
from src.app.routers.registration import router as registration_router
from src.app.routers.uap import router as uap_router
from src.app.routers.user import router as user_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(registration_router)
api_router.include_router(user_router)
api_router.include_router(uap_router)

__all__ = ["api_router"]
