from __future__ import annotations

from app.agents.gemini import GeminiClient


async def test_gemini_client_returns_fallback_without_api_key() -> None:
    fallback = {"ok": True}
    client = GeminiClient(api_key="")

    assert await client.json_completion("Return JSON", fallback) == fallback
