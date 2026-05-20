"""Google Sites connector -- sync pages from a Google Sites site."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class GoogleSitesConnector(BaseConnector):
    """Sync pages from Google Sites via the Sites API."""

    def __init__(self, site_id: str, token: str | None = None):
        self.site_id = site_id
        self._token = token or os.environ.get("GOOGLE_SITES_TOKEN")
        if not self._token:
            raise ValueError("Set GOOGLE_SITES_TOKEN env var (OAuth2 access token).")
        self._http = httpx.Client(
            base_url="https://sites.googleapis.com/v1",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        resp = self._http.get(f"/sites/{self.site_id}/pages")
        resp.raise_for_status()
        pages = resp.json().get("pages", [])
        entries: list[ManifestEntry] = []
        for page in pages:
            title = page.get("title", "untitled")
            html = page.get("html", "")
            text = f"# {title}\n\n{html}"
            filename = f"{page.get('name', title)}.md"
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_gsites_source(source: str) -> dict[str, str]:
    site_id = source.removeprefix("gsites:")
    if not site_id:
        raise ValueError("Expected: gsites:<site-id>")
    return {"site_id": site_id}
