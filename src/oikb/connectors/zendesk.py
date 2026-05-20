"""Zendesk connector — sync help center articles to a Knowledge Base.

Auth via ZENDESK_SUBDOMAIN, ZENDESK_USER, ZENDESK_TOKEN env vars.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class ZendeskConnector(BaseConnector):
    """Sync articles from Zendesk Help Center."""

    def __init__(self, subdomain: str | None = None, user: str | None = None, token: str | None = None):
        self._subdomain = subdomain or os.environ.get("ZENDESK_SUBDOMAIN", "")
        self._user = user or os.environ.get("ZENDESK_USER", "")
        self._token = token or os.environ.get("ZENDESK_TOKEN", "")
        if not self._subdomain or not self._token:
            raise ValueError("Zendesk credentials required. Set ZENDESK_SUBDOMAIN and ZENDESK_TOKEN env vars.")
        self._http = httpx.Client(
            base_url=f"https://{self._subdomain}.zendesk.com/api/v2",
            auth=(f"{self._user}/token", self._token),
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        page = 1
        while True:
            resp = self._http.get("/help_center/articles.json", params={"page": page, "per_page": 100})
            resp.raise_for_status()
            data = resp.json()
            for article in data.get("articles", []):
                title = re.sub(r'[<>:"/\\|?*]', "_", article.get("title", "Untitled"))
                body = re.sub(r"<[^>]+>", " ", article.get("body", "") or "")
                text = f"# {title}\n\n{body}"
                filename = f"{article['id']}_{title[:50]}.txt"
                checksum = hashlib.sha256(f"{article['id']}:{article.get('updated_at', '')}".encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
            if not data.get("next_page"):
                break
            page += 1
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Article not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_zendesk_source(source: str) -> dict[str, str | None]:
    subdomain = source.removeprefix("zendesk:")
    if not subdomain:
        raise ValueError("Invalid Zendesk source. Expected: zendesk:<subdomain>")
    return {"subdomain": subdomain}
