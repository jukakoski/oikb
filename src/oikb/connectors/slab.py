"""Slab connector -- sync posts from a Slab organization via GraphQL."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class SlabConnector(BaseConnector):
    """Sync posts from Slab."""

    def __init__(self, org: str | None = None, token: str | None = None):
        self._token = token or os.environ.get("SLAB_TOKEN")
        if not self._token:
            raise ValueError("Set SLAB_TOKEN env var.")
        self._org = org or os.environ.get("SLAB_ORG", "")
        base = f"https://{self._org}.slab.com" if self._org else "https://api.slab.com"
        self._http = httpx.Client(
            base_url=base,
            headers={"Authorization": self._token, "Content-Type": "application/json"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        query = '{ organization { posts { id title content } } }'
        resp = self._http.post("/graphql", json={"query": query})
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("organization", {}).get("posts", [])
        entries: list[ManifestEntry] = []
        for post in posts:
            title = post.get("title", "untitled")
            content = post.get("content", "")
            text = f"# {title}\n\n{content}"
            filename = f"{post['id']}.md"
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_slab_source(source: str) -> dict[str, str | None]:
    org = source.removeprefix("slab:") or None
    return {"org": org}
