from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@asynccontextmanager
async def http_client(timeout: float = 20.0) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        yield client


@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=0.5, min=1, max=8),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def request_json(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    **kwargs: Any,
) -> Any:
    response = await client.request(method, url, **kwargs)
    response.raise_for_status()
    return response.json()
