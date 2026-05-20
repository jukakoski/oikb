"""Microsoft Teams connector — sync channel messages to a Knowledge Base.

Auth via Microsoft Graph API using app credentials.
Set TEAMS_TENANT_ID, TEAMS_CLIENT_ID, TEAMS_CLIENT_SECRET env vars.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class TeamsConnector(BaseConnector):
    """Sync messages from a Microsoft Teams channel."""

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
        self._text: str = ""

    def build_manifest(self) -> list[ManifestEntry]:
        messages: list[dict] = []
        url = f"/teams/{self.team_id}/channels/{self.channel_id}/messages"
        while url and len(messages) < 1000:
            resp = self._http.get(url)
            resp.raise_for_status()
            data = resp.json()
            messages.extend(data.get("value", []))
            url = data.get("@odata.nextLink", "").replace("https://graph.microsoft.com/v1.0", "") if data.get("@odata.nextLink") else None

        if not messages:
            return []

        lines = []
        for msg in messages:
            sender = msg.get("from", {}).get("user", {}).get("displayName", "unknown")
            body = msg.get("body", {}).get("content", "")
            ts = msg.get("createdDateTime", "")
            lines.append(f"[{ts}] {sender}: {body}")

        self._text = "\n".join(lines)
        checksum = hashlib.sha256(self._text.encode()).hexdigest()[:16]

        info = self._http.get(f"/teams/{self.team_id}/channels/{self.channel_id}")
        name = info.json().get("displayName", self.channel_id) if info.status_code == 200 else self.channel_id

        return [ManifestEntry(filename=f"{name}.txt", path="", checksum=checksum, size=len(self._text.encode()))]

    def read_file(self, path: str, filename: str) -> bytes:
        return self._text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_teams_source(source: str) -> dict[str, str | None]:
    """Parse teams:team-id/channel-id."""
    source = source.removeprefix("teams:")
    parts = source.split("/", 1)
    if len(parts) < 2:
        raise ValueError("Invalid Teams source. Expected: teams:<team-id>/<channel-id>")
    return {"team_id": parts[0], "channel_id": parts[1]}
