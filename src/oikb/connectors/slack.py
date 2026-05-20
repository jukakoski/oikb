"""Slack connector — sync channel history to a Knowledge Base.

Auth via SLACK_TOKEN env var (Bot User OAuth Token with channels:history scope).
Messages are split by day for incremental sync — past days never change.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class SlackConnector(BaseConnector):
    """Sync messages from a Slack channel, one file per day."""

    def __init__(self, channel_id: str, token: str | None = None, limit: int = 5000):
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
        self._channel_name: str = ""
        self._daily_texts: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        messages = self._fetch_history()
        if not messages:
            return []

        # Get channel name.
        info = self._http.get("/conversations.info", params={"channel": self.channel_id})
        self._channel_name = (
            info.json().get("channel", {}).get("name", self.channel_id)
            if info.status_code == 200
            else self.channel_id
        )

        # Group messages by date.
        by_day: dict[str, list[dict]] = defaultdict(list)
        for msg in messages:
            ts = float(msg.get("ts", "0"))
            day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            by_day[day].append(msg)

        entries: list[ManifestEntry] = []
        for day, day_msgs in sorted(by_day.items()):
            lines = []
            for msg in sorted(day_msgs, key=lambda m: m.get("ts", "")):
                user = msg.get("user", "unknown")
                text = msg.get("text", "")
                ts = msg.get("ts", "")
                lines.append(f"[{ts}] {user}: {text}")

            content = "\n".join(lines)
            self._daily_texts[day] = content
            checksum = hashlib.sha256(content.encode()).hexdigest()[:16]

            entries.append(
                ManifestEntry(
                    filename=f"{self._channel_name}_{day}.txt",
                    path="",
                    checksum=checksum,
                    size=len(content.encode()),
                )
            )

        return entries

    def _fetch_history(self) -> list[dict]:
        messages: list[dict] = []
        cursor = None
        while len(messages) < self.limit:
            params: dict[str, Any] = {
                "channel": self.channel_id,
                "limit": min(200, self.limit - len(messages)),
            }
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

    def read_file(self, path: str, filename: str) -> bytes:
        # Extract date from filename: channel_YYYY-MM-DD.txt
        for day, text in self._daily_texts.items():
            if day in filename:
                return text.encode("utf-8")
        raise FileNotFoundError(f"Day not found: {filename}")

    def close(self) -> None:
        self._http.close()


def parse_slack_source(source: str) -> dict[str, str | None]:
    channel_id = source.removeprefix("slack:")
    if not channel_id:
        raise ValueError("Invalid Slack source. Expected: slack:<channel-id>")
    return {"channel_id": channel_id}
