"""Discourse connector — sync forum topics to a Knowledge Base.

Auth via DISCOURSE_URL, DISCOURSE_API_KEY, DISCOURSE_API_USERNAME env vars.
"""

from __future__ import annotations

import hashlib
import os
import re

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class DiscourseConnector(BaseConnector):
    """Sync topics from a Discourse forum."""

    def __init__(self, base_url: str | None = None, api_key: str | None = None, username: str | None = None, category: str | None = None):
        self._url = (base_url or os.environ.get("DISCOURSE_URL", "")).rstrip("/")
        self._key = api_key or os.environ.get("DISCOURSE_API_KEY", "")
        self._user = username or os.environ.get("DISCOURSE_API_USERNAME", "system")
        self.category = category
        if not self._url or not self._key:
            raise ValueError("Discourse credentials required. Set DISCOURSE_URL and DISCOURSE_API_KEY.")
        self._http = httpx.Client(base_url=self._url, headers={"Api-Key": self._key, "Api-Username": self._user}, timeout=30.0)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        page = 0
        url = f"/c/{self.category}.json" if self.category else "/latest.json"
        while True:
            resp = self._http.get(url, params={"page": page})
            resp.raise_for_status()
            topics = resp.json().get("topic_list", {}).get("topics", [])
            if not topics:
                break
            for topic in topics:
                title = re.sub(r'[<>:"/\\|?*]', "_", topic.get("title", "Untitled"))
                filename = f"{topic['id']}_{title[:50]}.txt"
                checksum = hashlib.sha256(f"{topic['id']}:{topic.get('last_posted_at', '')}".encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=0))
            page += 1
            if page > 50:
                break
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        topic_id = filename.split("_")[0]
        resp = self._http.get(f"/t/{topic_id}.json")
        resp.raise_for_status()
        data = resp.json()
        title = data.get("title", "")
        posts = data.get("post_stream", {}).get("posts", [])
        lines = [f"# {title}\n"]
        for post in posts:
            user = post.get("username", "")
            body = re.sub(r"<[^>]+>", " ", post.get("cooked", ""))
            lines.append(f"\n**{user}:**\n{body}")
        return "\n".join(lines).encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_discourse_source(source: str) -> dict[str, str | None]:
    cat = source.removeprefix("discourse:")
    return {"category": cat if cat else None}
