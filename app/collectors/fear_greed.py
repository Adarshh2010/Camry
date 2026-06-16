from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.http import http_client, request_json


class FearGreedClient:
    async def latest(self) -> dict[str, Any]:
        async with http_client() as client:
            return await request_json(
                client, "GET", str(settings.fear_greed_url), params={"limit": 1}
            )
