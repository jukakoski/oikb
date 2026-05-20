"""XenForo connector -- sync forum threads."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class XenForoConnector(BaseConnector):
    """Sync threads from a XenForo forum."""

    def __init__(self, forum_id: str | None = None, token: str | None = None, base_url: str | None = None):
        self._token = token or os.environ.get("XENFORO_KEY")
        self._base = base_url or os.environ.get("XENFORO_URL")
        if not self._token or not self._base:
            raise ValueError("Set XENFORO_URL and XENFORO_KEY env vars.")
        self._forum_id = forum_id
        self._http = httpx.Client(
            base_url=self._base.rstrip("/"),
            headers={"XF-Api-Key": self._token},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        params = {}
        if self._forum_id:
            params["node_id"] = self._forum_id
        resp = self._http.get("/api/threads", params=params)
        resp.raise_for_status()
        threads = resp.json().get("threads", [])
        entries: list[ManifestEntry] = []
        for thread in threads:
            title = thread.get("title", "")
            # Fetch first post content.
            first_post = thread.get("first_post", {})
            body = first_post.get("message", "")
            text = f"# {title}\n\n{body}"
            filename = f"thread_{thread['thread_id']}.md"
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_xenforo_source(source: str) -> dict[str, str | None]:
    forum_id = source.removeprefix("xenforo:") or None
    return {"forum_id": forum_id}
