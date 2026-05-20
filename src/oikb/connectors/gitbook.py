"""GitBook connector — sync pages from a GitBook space.

Auth via GITBOOK_TOKEN env var.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class GitBookConnector(BaseConnector):
    def __init__(self, space_id: str, token: str | None = None):
        self.space_id = space_id
        self._token = token or os.environ.get("GITBOOK_TOKEN")
        if not self._token:
            raise ValueError("GitBook token required. Set GITBOOK_TOKEN env var.")
        self._http = httpx.Client(base_url="https://api.gitbook.com/v1", headers={"Authorization": f"Bearer {self._token}"}, timeout=30.0)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        resp = self._http.get(f"/spaces/{self.space_id}/content")
        resp.raise_for_status()
        pages = resp.json().get("pages", [])
        self._walk_pages(pages, "", entries)
        entries.sort(key=lambda e: e.display_path)
        return entries

    def _walk_pages(self, pages: list[dict], prefix: str, entries: list[ManifestEntry]) -> None:
        for page in pages:
            title = re.sub(r'[<>:"/\\|?*]', "_", page.get("title", "Untitled"))
            pid = page.get("id", "")
            filename = f"{title}.txt"
            checksum = hashlib.sha256(f"{pid}:{page.get('updatedAt', '')}".encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path=prefix, checksum=checksum, size=0))
            self._cache[f"{prefix}/{filename}" if prefix else filename] = pid
            if page.get("pages"):
                sub = f"{prefix}/{title}" if prefix else title
                self._walk_pages(page["pages"], sub, entries)

    def read_file(self, path: str, filename: str) -> bytes:
        key = f"{path}/{filename}" if path else filename
        pid = self._cache.get(key)
        if not pid:
            raise FileNotFoundError(f"Page not found: {key}")
        resp = self._http.get(f"/spaces/{self.space_id}/content/page/{pid}")
        resp.raise_for_status()
        data = resp.json()
        md = data.get("markdown", "") or data.get("title", "")
        return md.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_gitbook_source(source: str) -> dict[str, str | None]:
    sid = source.removeprefix("gitbook:")
    if not sid:
        raise ValueError("Expected: gitbook:<space-id>")
    return {"space_id": sid}
