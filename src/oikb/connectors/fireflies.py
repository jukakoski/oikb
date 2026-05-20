"""Fireflies connector -- sync meeting transcripts via GraphQL."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class FirefliesConnector(BaseConnector):
    """Sync meeting transcripts from Fireflies.ai."""

    def __init__(self, token: str | None = None):
        self._token = token or os.environ.get("FIREFLIES_TOKEN")
        if not self._token:
            raise ValueError("Set FIREFLIES_TOKEN env var.")
        self._http = httpx.Client(
            base_url="https://api.fireflies.ai",
            headers={"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        query = """{ transcripts { id title date organizer_email sentences { speaker_name text } } }"""
        resp = self._http.post("/graphql", json={"query": query})
        resp.raise_for_status()
        transcripts = resp.json().get("data", {}).get("transcripts", [])
        entries: list[ManifestEntry] = []
        for t in transcripts:
            title = t.get("title", "Meeting")
            lines = [f"{s['speaker_name']}: {s['text']}" for s in t.get("sentences", []) if s.get("text")]
            text = f"# {title}\n\nDate: {t.get('date', '')}\n\n" + "\n".join(lines)
            filename = f"{t['id']}.md"
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()
