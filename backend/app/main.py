"""FastAPI application entrypoint."""

from fastapi import FastAPI

from backend.app.api.router import api_router
from backend.app.core.settings import get_settings
from backend.app.schemas.api import ApiResponse, ok_response


def create_app() -> FastAPI:
    """Build the FastAPI application."""
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    @app.get("/", response_model=ApiResponse, tags=["meta"])
    def root() -> ApiResponse:
        return ok_response(
            message="backend_entrypoint_ready",
            data={
                "service": settings.app_name,
                "version": settings.app_version,
                "api_prefix": settings.api_prefix,
            },
        )

    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
