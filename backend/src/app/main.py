from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.app.core.config import get_settings
from src.app.routers import api_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OptiFlow API", version="0.1.0")

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
