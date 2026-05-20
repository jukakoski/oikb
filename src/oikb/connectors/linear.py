"""Linear connector — sync issues from a Linear team to a Knowledge Base.

Auth via LINEAR_TOKEN env var (API key).
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class LinearConnector(BaseConnector):
    """Sync issues from a Linear team."""

    def __init__(self, team_key: str, token: str | None = None):
        self.team_key = team_key
        self._token = token or os.environ.get("LINEAR_TOKEN")
        if not self._token:
            raise ValueError("Linear API key required. Set LINEAR_TOKEN env var.")
        self._http = httpx.Client(
            base_url="https://api.linear.app",
            headers={"Authorization": self._token, "Content-Type": "application/json"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        cursor = None
        while True:
            after = f', after: "{cursor}"' if cursor else ""
            query = f'''{{ team(id: "{self.team_key}") {{ issues(first: 100{after}) {{ nodes {{ id identifier title description state {{ name }} updatedAt }} pageInfo {{ hasNextPage endCursor }} }} }} }}'''
            resp = self._http.post("/graphql", json={"query": query})
            resp.raise_for_status()
            data = resp.json().get("data", {}).get("team", {}).get("issues", {})
            for issue in data.get("nodes", []):
                text = f"# [{issue['identifier']}] {issue['title']}\nStatus: {issue.get('state', {}).get('name', '')}\n\n{issue.get('description', '') or ''}"
                filename = f"{issue['identifier']}.txt"
                checksum = hashlib.sha256(f"{issue['id']}:{issue.get('updatedAt', '')}".encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
            pi = data.get("pageInfo", {})
            if not pi.get("hasNextPage"):
                break
            cursor = pi.get("endCursor")
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Issue not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_linear_source(source: str) -> dict[str, str | None]:
    team_key = source.removeprefix("linear:")
    if not team_key:
        raise ValueError("Invalid Linear source. Expected: linear:<team-id>")
    return {"team_key": team_key}
