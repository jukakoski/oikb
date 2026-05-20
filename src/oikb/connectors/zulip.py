"""Zulip connector -- sync messages from a Zulip stream, split by day."""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from datetime import datetime, timezone

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class ZulipConnector(BaseConnector):
    """Sync messages from a Zulip stream, one file per day."""

    def __init__(self, stream: str | None = None, token: str | None = None, base_url: str | None = None):
        self._email = os.environ.get("ZULIP_EMAIL", "")
        self._key = token or os.environ.get("ZULIP_KEY", "")
        self._base = base_url or os.environ.get("ZULIP_URL", "")
        if not self._email or not self._key or not self._base:
            raise ValueError("Set ZULIP_URL, ZULIP_EMAIL, ZULIP_KEY env vars.")
        self._stream = stream
        self._http = httpx.Client(
            base_url=self._base.rstrip("/"),
            auth=(self._email, self._key),
            timeout=30.0,
        )
        self._daily_texts: dict[str, str] = {}
        self._stream_name: str = ""

    def build_manifest(self) -> list[ManifestEntry]:
        narrow = [{"operator": "stream", "operand": self._stream}] if self._stream else []
        params = {"narrow": str(narrow), "num_before": 5000, "num_after": 0, "anchor": "newest"}
        resp = self._http.get("/api/v1/messages", params=params)
        resp.raise_for_status()
        messages = resp.json().get("messages", [])
        if not messages:
            return []

        self._stream_name = self._stream or "all"
        by_day: dict[str, list[dict]] = defaultdict(list)
        for msg in messages:
            ts = msg.get("timestamp", 0)
            day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            by_day[day].append(msg)

        entries: list[ManifestEntry] = []
        for day, day_msgs in sorted(by_day.items()):
            lines = []
            for msg in sorted(day_msgs, key=lambda m: m.get("timestamp", 0)):
                sender = msg.get("sender_full_name", "unknown")
                topic = msg.get("subject", "")
                content = msg.get("content", "")
                lines.append(f"[{topic}] {sender}: {content}")
            text = "\n".join(lines)
            self._daily_texts[day] = text
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(
                filename=f"{self._stream_name}_{day}.txt", path="",
                checksum=checksum, size=len(text.encode()),
            ))
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        for day, text in self._daily_texts.items():
            if day in filename:
                return text.encode("utf-8")
        raise FileNotFoundError(f"Day not found: {filename}")

    def close(self) -> None:
        self._http.close()


def parse_zulip_source(source: str) -> dict[str, str | None]:
    stream = source.removeprefix("zulip:") or None
    return {"stream": stream}
