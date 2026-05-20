"""Microsoft Teams connector — sync channel messages to a Knowledge Base.

Auth via Microsoft Graph API using app credentials.
Set TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET env vars.
Messages are split by day for incremental sync.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class TeamsConnector(BaseConnector):
    """Sync messages from a Microsoft Teams channel, one file per day."""

    def __init__(self, team_id: str, channel_id: str,
                 tenant_id: str | None = None, client_id: str | None = None, client_secret: str | None = None):
        self.team_id = team_id
        self.channel_id = channel_id

        tid = tenant_id or os.environ.get("TEAMS_TENANT_ID", "")
        cid = client_id or os.environ.get("TEAMS_CLIENT_ID", "")
        secret = client_secret or os.environ.get("TEAMS_CLIENT_SECRET", "")
        if not all([tid, cid, secret]):
            raise ValueError("Teams credentials required. Set TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET.")

        token_resp = httpx.post(f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token", data={
            "grant_type": "client_credentials", "client_id": cid, "client_secret": secret,
            "scope": "https://graph.microsoft.com/.default",
        })
        token_resp.raise_for_status()

        self._http = httpx.Client(
            base_url="https://graph.microsoft.com/v1.0",
            headers={"Authorization": f"Bearer {token_resp.json()['access_token']}"},
            timeout=30.0,
        )
        self._channel_name: str = ""
        self._daily_texts: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        messages = self._fetch_messages()
        if not messages:
            return []

        info = self._http.get(f"/teams/{self.team_id}/channels/{self.channel_id}")
        self._channel_name = (
            info.json().get("displayName", self.channel_id)
            if info.status_code == 200
            else self.channel_id
        )

        by_day: dict[str, list[dict]] = defaultdict(list)
        for msg in messages:
            ts = msg.get("createdDateTime", "")[:10]
            if not ts:
                continue
            by_day[ts].append(msg)

        entries: list[ManifestEntry] = []
        for day, day_msgs in sorted(by_day.items()):
            lines = []
            for msg in sorted(day_msgs, key=lambda m: m.get("createdDateTime", "")):
                sender = msg.get("from", {}).get("user", {}).get("displayName", "unknown")
                body = msg.get("body", {}).get("content", "")
                lines.append(f"[{msg.get('createdDateTime', '')}] {sender}: {body}")

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
        url = f"/teams/{self.team_id}/channels/{self.channel_id}/messages"
        while url and len(messages) < 5000:
            resp = self._http.get(url)
            resp.raise_for_status()
            data = resp.json()
            messages.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink", "")
            url = next_link.replace("https://graph.microsoft.com/v1.0", "") if next_link else None
        return messages

    def read_file(self, path: str, filename: str) -> bytes:
        for day, text in self._daily_texts.items():
            if day in filename:
                return text.encode("utf-8")
        raise FileNotFoundError(f"Day not found: {filename}")

    def close(self) -> None:
        self._http.close()


def parse_teams_source(source: str) -> dict[str, str | None]:
    source = source.removeprefix("teams:")
    parts = source.split("/", 1)
    if len(parts) < 2:
        raise ValueError("Invalid Teams source. Expected: teams:<team-id>/<channel-id>")
    return {"team_id": parts[0], "channel_id": parts[1]}
