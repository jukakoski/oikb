"""Discord connector — sync channel messages to a Knowledge Base.

Auth via DISCORD_TOKEN env var (Bot token with Message Content intent).
Messages are split by day for incremental sync.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import datetime
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class DiscordConnector(BaseConnector):
    """Sync messages from a Discord channel, one file per day."""

    def __init__(self, channel_id: str, token: str | None = None, limit: int = 5000):
        self.channel_id = channel_id
        self.limit = limit
        self._token = token or os.environ.get("DISCORD_TOKEN")
        if not self._token:
            raise ValueError("Discord bot token required. Set DISCORD_TOKEN env var.")

        self._http = httpx.Client(
            base_url="https://discord.com/api/v10",
            headers={"Authorization": f"Bot {self._token}"},
            timeout=30.0,
        )
        self._channel_name: str = ""
        self._daily_texts: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        messages = self._fetch_messages()
        if not messages:
            return []

        info = self._http.get(f"/channels/{self.channel_id}")
        self._channel_name = (
            info.json().get("name", self.channel_id)
            if info.status_code == 200
            else self.channel_id
        )

        # Group by day.
        by_day: dict[str, list[dict]] = defaultdict(list)
        for msg in messages:
            ts = msg.get("timestamp", "")[:10]  # YYYY-MM-DD from ISO string.
            if not ts:
                continue
            by_day[ts].append(msg)

        entries: list[ManifestEntry] = []
        for day, day_msgs in sorted(by_day.items()):
            lines = []
            for msg in sorted(day_msgs, key=lambda m: m.get("timestamp", "")):
                author = msg.get("author", {}).get("username", "unknown")
                content = msg.get("content", "")
                lines.append(f"[{msg.get('timestamp', '')}] {author}: {content}")

            text = "\n".join(lines)
            self._daily_texts[day] = text
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]

            entries.append(
                ManifestEntry(
                    filename=f"{self._channel_name}_{day}.txt",
                    path="",
                    checksum=checksum,
                    size=len(text.encode()),
                )
            )

        return entries

    def _fetch_messages(self) -> list[dict]:
        messages: list[dict] = []
        before = None
        while len(messages) < self.limit:
            params: dict[str, Any] = {"limit": min(100, self.limit - len(messages))}
            if before:
                params["before"] = before
            resp = self._http.get(f"/channels/{self.channel_id}/messages", params=params)
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            messages.extend(batch)
            before = batch[-1]["id"]
        return messages

    def read_file(self, path: str, filename: str) -> bytes:
        for day, text in self._daily_texts.items():
            if day in filename:
                return text.encode("utf-8")
        raise FileNotFoundError(f"Day not found: {filename}")

    def close(self) -> None:
        self._http.close()


def parse_discord_source(source: str) -> dict[str, str | None]:
    channel_id = source.removeprefix("discord:")
    if not channel_id:
        raise ValueError("Invalid Discord source. Expected: discord:<channel-id>")
    return {"channel_id": channel_id}
