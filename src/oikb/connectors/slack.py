"""Slack connector — sync channel history to a Knowledge Base.

Auth via SLACK_TOKEN env var (Bot User OAuth Token with channels:history scope).
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class SlackConnector(BaseConnector):
    """Sync messages from a Slack channel."""

    def __init__(self, channel_id: str, token: str | None = None, limit: int = 1000):
        self.channel_id = channel_id
        self.limit = limit
        self._token = token or os.environ.get("SLACK_TOKEN")
        if not self._token:
            raise ValueError("Slack token required. Set SLACK_TOKEN env var.")

        self._http = httpx.Client(
            base_url="https://slack.com/api",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        self._messages: list[dict] = []

    def build_manifest(self) -> list[ManifestEntry]:
        self._messages = self._fetch_history()
        if not self._messages:
            return []

        text = self._format_messages(self._messages)
        checksum = hashlib.sha256(text.encode()).hexdigest()[:16]

        # Get channel name.
        info = self._http.get("/conversations.info", params={"channel": self.channel_id})
        name = info.json().get("channel", {}).get("name", self.channel_id) if info.status_code == 200 else self.channel_id

        return [ManifestEntry(filename=f"{name}.txt", path="", checksum=checksum, size=len(text.encode()))]

    def _fetch_history(self) -> list[dict]:
        messages: list[dict] = []
        cursor = None
        while len(messages) < self.limit:
            params: dict[str, Any] = {"channel": self.channel_id, "limit": min(200, self.limit - len(messages))}
            if cursor:
                params["cursor"] = cursor
            resp = self._http.get("/conversations.history", params=params)
            resp.raise_for_status()
            data = resp.json()
            messages.extend(data.get("messages", []))
            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
        return messages

    def _format_messages(self, messages: list[dict]) -> str:
        lines = []
        for msg in reversed(messages):
            user = msg.get("user", "unknown")
            text = msg.get("text", "")
            ts = msg.get("ts", "")
            lines.append(f"[{ts}] {user}: {text}")
        return "\n".join(lines)

    def read_file(self, path: str, filename: str) -> bytes:
        return self._format_messages(self._messages).encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_slack_source(source: str) -> dict[str, str | None]:
    channel_id = source.removeprefix("slack:")
    if not channel_id:
        raise ValueError("Invalid Slack source. Expected: slack:<channel-id>")
    return {"channel_id": channel_id}
