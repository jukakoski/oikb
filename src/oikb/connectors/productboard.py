"""ProductBoard connector -- sync features and notes."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class ProductBoardConnector(BaseConnector):
    """Sync features from ProductBoard."""

    def __init__(self, token: str | None = None):
        self._token = token or os.environ.get("PRODUCTBOARD_TOKEN")
        if not self._token:
            raise ValueError("Set PRODUCTBOARD_TOKEN env var.")
        self._http = httpx.Client(
            base_url="https://api.productboard.com",
            headers={"Authorization": f"Bearer {self._token}", "X-Version": "1"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        url = "/features"
        while url:
            resp = self._http.get(url)
            resp.raise_for_status()
            data = resp.json()
            for feature in data.get("data", []):
                name = feature.get("name", "untitled")
                desc = feature.get("description", "")
                status = feature.get("status", {}).get("name", "")
                text = f"# {name}\n\nStatus: {status}\n\n{desc}"
                filename = f"{feature['id']}.md"
                checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
            url = data.get("links", {}).get("next")
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()
