from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.routers import api_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="OptiFlow API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(
            {settings.frontend_url.rstrip("/"), "http://localhost:5173"}
        ),
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
