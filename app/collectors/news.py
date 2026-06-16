from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx
from telegram import Bot

from app.core.config import settings
from app.core.http import http_client, request_json
from app.core.logging import logger


class NewsCollector:
    def __init__(self, feeds: list[str] | None = None) -> None:
        self.feeds = feeds or settings.rss_feeds

    async def collect_all(self) -> list[dict]:
        rows = await self.collect_rss()
        rows.extend(await self.collect_reddit())
        rows.extend(await self.collect_telegram_updates())
        return rows

    async def collect_rss(self) -> list[dict]:
        rows: list[dict] = []
        async with http_client() as client:
            for feed_url in self.feeds:
                try:
                    text = await request_text(client, feed_url)
                except httpx.HTTPError as exc:
                    logger.warning("rss_feed_skipped", feed_url=feed_url, error=str(exc))
                    continue
                parsed = feedparser.parse(text)
                for entry in parsed.entries:
                    url = str(entry.get("link", "")).strip()
                    title = str(entry.get("title", "")).strip()
                    if not url or not title:
                        continue
                    published = parse_published(entry)
                    content = str(entry.get("summary", "") or entry.get("description", ""))
                    rows.append(
                        {
                            "source": parsed.feed.get("title", feed_url)[:128],
                            "title": title[:512],
                            "url": url[:1024],
                            "content": content,
                            "published_at": published,
                            "dedupe_hash": dedupe_hash(title, url),
                            "raw": trim_raw(entry),
                        }
                    )
        return rows

    async def collect_reddit(self, limit: int = 25) -> list[dict]:
        rows: list[dict] = []
        async with http_client() as client:
            for community in settings.reddit_communities:
                try:
                    data = await request_json(
                        client,
                        "GET",
                        f"https://www.reddit.com/r/{community}/new.json",
                        params={"limit": limit},
                        headers={"User-Agent": "hyperliquid-research-platform/0.1"},
                    )
                except httpx.HTTPError as exc:
                    logger.warning("reddit_community_skipped", community=community, error=str(exc))
                    continue
                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    title = str(post.get("title", "")).strip()
                    permalink = post.get("permalink")
                    if not title or not permalink:
                        continue
                    url = f"https://www.reddit.com{permalink}"
                    created = post.get("created_utc")
                    rows.append(
                        {
                            "source": f"reddit/r/{community}",
                            "title": title[:512],
                            "url": url[:1024],
                            "content": post.get("selftext") or post.get("url"),
                            "published_at": datetime.fromtimestamp(created, tz=UTC)
                            if created
                            else None,
                            "dedupe_hash": dedupe_hash(title, url),
                            "raw": {
                                "score": post.get("score"),
                                "num_comments": post.get("num_comments"),
                                "id": post.get("id"),
                            },
                        }
                    )
        return rows

    async def collect_telegram_updates(self) -> list[dict]:
        if not settings.telegram_bot_token:
            return []
        bot = Bot(settings.telegram_bot_token)
        updates = await bot.get_updates(timeout=1)
        allowed_channels = set(settings.telegram_channel_usernames)
        rows: list[dict] = []
        for update in updates:
            message = update.channel_post or update.message
            if not message or not message.chat:
                continue
            username = message.chat.username
            if allowed_channels and username not in allowed_channels:
                continue
            text = message.text or message.caption
            if not text:
                continue
            channel = username or str(message.chat.id)
            url = f"telegram://{channel}/{message.message_id}"
            rows.append(
                {
                    "source": f"telegram/{channel}",
                    "title": text.splitlines()[0][:512],
                    "url": url[:1024],
                    "content": text,
                    "published_at": message.date,
                    "dedupe_hash": dedupe_hash(text[:512], url),
                    "raw": {"chat_id": message.chat.id, "message_id": message.message_id},
                }
            )
        return rows


async def request_text(client: Any, url: str) -> str:
    response = await client.get(url)
    response.raise_for_status()
    return response.text


def parse_published(entry: Any) -> datetime | None:
    value = entry.get("published") or entry.get("updated")
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def dedupe_hash(title: str, url: str) -> str:
    normalized = f"{title.strip().lower()}|{url.strip().lower()}"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def trim_raw(entry: Any) -> dict:
    return {
        "id": entry.get("id"),
        "tags": [tag.get("term") for tag in entry.get("tags", [])],
        "authors": entry.get("authors"),
    }
