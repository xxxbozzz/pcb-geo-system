"""System status service."""

from __future__ import annotations

import os

from backend.app.core.settings import get_settings
from backend.app.db.mysql import database
from core.build_info import format_build_label


class SystemService:
    """Expose lightweight backend system status."""

    def get_status(self) -> dict[str, object]:
        settings = get_settings()
        return {
            "environment": settings.app_env,
            "debug": settings.app_debug,
            "database": "ok" if database.ping() else "error",
            "deepseek_api_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
            "build": format_build_label(),
        }


system_service = SystemService()
