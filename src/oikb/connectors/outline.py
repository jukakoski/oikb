"""Outline connector -- sync documents from an Outline wiki."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class OutlineConnector(BaseConnector):
    """Sync documents from Outline."""

    def __init__(self, collection: str | None = None, token: str | None = None, base_url: str | None = None):
        self._token = token or os.environ.get("OUTLINE_TOKEN")
        self._base = base_url or os.environ.get("OUTLINE_URL", "https://app.getoutline.com")
        if not self._token:
            raise ValueError("Set OUTLINE_TOKEN env var.")
        self._collection = collection
        self._http = httpx.Client(
            base_url=self._base,
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        params: dict = {"limit": 100}
        if self._collection:
            # Resolve collection by name.
            cols = self._http.post("/api/collections.list", json={}).json().get("data", [])
            col = next((c for c in cols if c.get("name") == self._collection or c.get("id") == self._collection), None)
            if col:
                params["collectionId"] = col["id"]

        resp = self._http.post("/api/documents.list", json=params)
        resp.raise_for_status()
        docs = resp.json().get("data", [])
        entries: list[ManifestEntry] = []
        for doc in docs:
            title = doc.get("title", "untitled")
            text = doc.get("text", "")
            content = f"# {title}\n\n{text}"
            filename = f"{doc['id']}.md"
            checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(content.encode())))
            self._cache[filename] = content
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_outline_source(source: str) -> dict[str, str | None]:
    collection = source.removeprefix("outline:") or None
    return {"collection": collection}
