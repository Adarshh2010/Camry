from __future__ import annotations

import json
from typing import Any

from google import genai

from app.core.config import settings
from app.core.logging import logger


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = settings.gemini_api_key if api_key is None else api_key
        self.model = model or settings.gemini_model
        self._client = genai.Client(api_key=self.api_key) if self.api_key else None

    async def json_completion(self, prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        if self._client is None:
            return fallback
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model,
                contents=prompt,
            )
        except Exception as exc:
            logger.warning("gemini_completion_failed", model=self.model, error=str(exc))
            return fallback
        text = response.text or ""
        try:
            return json.loads(extract_json(text))
        except json.JSONDecodeError:
            return fallback | {"raw_text": text}


def extract_json(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]
