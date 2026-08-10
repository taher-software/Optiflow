import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.core.config import get_settings
from src.app.core.geo_timezone import warm_up as warm_up_geo_timezone
from src.app.routers import api_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Build the geocoding singletons (GeonamesCache/TimezoneFinder — ~1s,
    # CPU-bound) here, off the event loop via `asyncio.to_thread`, so the
    # first registration request never pays that cost inline and stalls
    # co-resident requests. Best-effort: a warm-up failure must never crash
    # boot, `warm_up` itself already logs and swallows its own errors, but a
    # second layer here guards against anything unexpected (e.g. the thread
    # itself failing to start).
    try:
        await asyncio.to_thread(warm_up_geo_timezone)
    except Exception:
        logger.warning("startup: geo_timezone warm-up failed", exc_info=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OptiFlow API", version="0.1.0", lifespan=_lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            {settings.frontend_url.rstrip("/"), "http://localhost:5173"}
        ),
        # Allow any local dev server (web on 5173, Expo web on 8081/19006, …) so
        # CORS preflights from the mobile/web dev tooling don't 400.
        allow_origin_regex=r"https?://(localhost|127\.0\.0\.1)(:\d+)?",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
