from fastapi import APIRouter

from src.app.routers.auth import router as auth_router
from src.app.routers.down_time import router as down_time_router
from src.app.routers.kpi import router as kpi_router
from src.app.routers.namespace import router as namespace_router
from src.app.routers.plan import router as plan_router
from src.app.routers.production_line import router as production_line_router
from src.app.routers.registration import router as registration_router
from src.app.routers.settings import router as settings_router
from src.app.routers.subscription import router as subscription_router
from src.app.routers.uap import router as uap_router
from src.app.routers.user import router as user_router
from src.app.routers.workers import router as workers_router
from src.app.routers.workstation import router as workstation_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(registration_router)
api_router.include_router(user_router)
api_router.include_router(uap_router)
api_router.include_router(production_line_router)
api_router.include_router(workstation_router)
api_router.include_router(down_time_router)
api_router.include_router(settings_router)
api_router.include_router(workers_router)
api_router.include_router(kpi_router)
api_router.include_router(plan_router)
api_router.include_router(subscription_router)
api_router.include_router(namespace_router)

__all__ = ["api_router"]
