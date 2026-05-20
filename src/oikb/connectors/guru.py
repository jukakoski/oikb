"""Guru connector — sync cards from Guru knowledge base.

Auth via GURU_USER, GURU_TOKEN env vars.
"""

from __future__ import annotations

import hashlib
import os
import re

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class GuruConnector(BaseConnector):
    def __init__(self, collection: str | None = None, user: str | None = None, token: str | None = None):
        self.collection = collection
        self._user = user or os.environ.get("GURU_USER", "")
        self._token = token or os.environ.get("GURU_TOKEN", "")
        if not self._token:
            raise ValueError("Guru token required. Set GURU_USER and GURU_TOKEN env vars.")
        self._http = httpx.Client(base_url="https://api.getguru.com/api/v1", auth=(self._user, self._token), timeout=30.0)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        resp = self._http.get("/search/cardmgr", params={"queryType": "cards"})
        resp.raise_for_status()
        for card in resp.json():
            title = re.sub(r'[<>:"/\\|?*]', "_", card.get("preferredPhrase", "Untitled"))
            content = re.sub(r"<[^>]+>", " ", card.get("content", "") or "")
            text = f"# {title}\n\n{content}"
            filename = f"{card.get('id', 'unknown')}_{title[:50]}.txt"
            checksum = hashlib.sha256(f"{card.get('id', '')}:{card.get('lastModified', '')}".encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_guru_source(source: str) -> dict[str, str | None]:
    col = source.removeprefix("guru:")
    return {"collection": col if col else None}
