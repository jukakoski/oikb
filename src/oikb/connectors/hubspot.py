"""HubSpot connector — sync knowledge articles and notes to a Knowledge Base.

Auth via HUBSPOT_TOKEN env var (private app access token).
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class HubSpotConnector(BaseConnector):
    """Sync knowledge base articles from HubSpot."""

    def __init__(self, token: str | None = None):
        self._token = token or os.environ.get("HUBSPOT_TOKEN")
        if not self._token:
            raise ValueError("HubSpot access token required. Set HUBSPOT_TOKEN env var.")
        self._http = httpx.Client(
            base_url="https://api.hubapi.com",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        after = None
        while True:
            params: dict[str, Any] = {"limit": 100}
            if after:
                params["after"] = after
            resp = self._http.get("/cms/v3/blogs/posts", params=params)
            resp.raise_for_status()
            data = resp.json()
            for post in data.get("results", []):
                title = re.sub(r'[<>:"/\\|?*]', "_", post.get("name", "Untitled"))
                body = re.sub(r"<[^>]+>", " ", post.get("postBody", "") or "")
                text = f"# {title}\n\n{body}"
                filename = f"{post['id']}_{title[:50]}.txt"
                checksum = hashlib.sha256(f"{post['id']}:{post.get('updated', '')}".encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
            paging = data.get("paging", {}).get("next", {})
            after = paging.get("after")
            if not after:
                break
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Post not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_hubspot_source(source: str) -> dict[str, str | None]:
    # hubspot: (no args, uses token)
    return {}
