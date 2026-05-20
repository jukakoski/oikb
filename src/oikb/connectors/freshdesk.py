"""Freshdesk connector — sync knowledge base articles from Freshdesk.

Auth via FRESHDESK_DOMAIN, FRESHDESK_TOKEN env vars.
"""

from __future__ import annotations

import hashlib
import os
import re

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class FreshdeskConnector(BaseConnector):
    """Sync knowledge articles from Freshdesk."""

    def __init__(self, domain: str | None = None, token: str | None = None):
        self._domain = domain or os.environ.get("FRESHDESK_DOMAIN", "")
        self._token = token or os.environ.get("FRESHDESK_TOKEN", "")
        if not self._domain or not self._token:
            raise ValueError("Freshdesk credentials required. Set FRESHDESK_DOMAIN and FRESHDESK_TOKEN.")
        self._http = httpx.Client(base_url=f"https://{self._domain}.freshdesk.com/api/v2", auth=(self._token, "X"), timeout=30.0)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        # Get all folders from all categories.
        cats = self._http.get("/solutions/categories").json()
        for cat in cats if isinstance(cats, list) else []:
            folders = self._http.get(f"/solutions/categories/{cat['id']}/folders").json()
            for folder in folders if isinstance(folders, list) else []:
                articles = self._http.get(f"/solutions/folders/{folder['id']}/articles").json()
                for article in articles if isinstance(articles, list) else []:
                    title = re.sub(r'[<>:"/\\|?*]', "_", article.get("title", "Untitled"))
                    body = re.sub(r"<[^>]+>", " ", article.get("description", "") or "")
                    text = f"# {title}\n\n{body}"
                    filename = f"{article['id']}_{title[:50]}.txt"
                    checksum = hashlib.sha256(f"{article['id']}:{article.get('updated_at', '')}".encode()).hexdigest()[:16]
                    entries.append(ManifestEntry(filename=filename, path=folder.get("name", ""), checksum=checksum, size=len(text.encode())))
                    self._cache[filename] = text
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Article not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_freshdesk_source(source: str) -> dict[str, str | None]:
    domain = source.removeprefix("freshdesk:")
    return {"domain": domain if domain else None}
