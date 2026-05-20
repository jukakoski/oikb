"""Discord connector — sync channel messages to a Knowledge Base.

Auth via DISCORD_TOKEN env var (Bot token with Message Content intent).
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class DiscordConnector(BaseConnector):
    """Sync messages from a Discord channel."""

    def __init__(self, channel_id: str, token: str | None = None, limit: int = 1000):
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
        self._text: str = ""

    def build_manifest(self) -> list[ManifestEntry]:
        messages = self._fetch_messages()
        if not messages:
            return []

        lines = []
        for msg in reversed(messages):
            author = msg.get("author", {}).get("username", "unknown")
            content = msg.get("content", "")
            ts = msg.get("timestamp", "")
            lines.append(f"[{ts}] {author}: {content}")

        self._text = "\n".join(lines)
        checksum = hashlib.sha256(self._text.encode()).hexdigest()[:16]

        # Get channel name.
        info = self._http.get(f"/channels/{self.channel_id}")
        name = info.json().get("name", self.channel_id) if info.status_code == 200 else self.channel_id

        return [ManifestEntry(filename=f"{name}.txt", path="", checksum=checksum, size=len(self._text.encode()))]

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
        return self._text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_discord_source(source: str) -> dict[str, str | None]:
    channel_id = source.removeprefix("discord:")
    if not channel_id:
        raise ValueError("Invalid Discord source. Expected: discord:<channel-id>")
    return {"channel_id": channel_id}
