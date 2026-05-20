"""Gong connector -- sync call transcripts from Gong."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class GongConnector(BaseConnector):
    """Sync call transcripts from Gong."""

    def __init__(self, access_key: str | None = None, secret: str | None = None):
        self._key = access_key or os.environ.get("GONG_ACCESS_KEY", "")
        self._secret = secret or os.environ.get("GONG_ACCESS_KEY_SECRET", "")
        if not self._key or not self._secret:
            raise ValueError("Set GONG_ACCESS_KEY and GONG_ACCESS_KEY_SECRET.")
        self._http = httpx.Client(
            base_url="https://api.gong.io/v2",
            auth=(self._key, self._secret),
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        resp = self._http.post("/calls/extensive", json={
            "filter": {},
            "contentSelector": {"exposedFields": {"content": {"structure": True}}},
        })
        resp.raise_for_status()
        entries: list[ManifestEntry] = []
        for call in resp.json().get("calls", []):
            meta = call.get("metaData", {})
            title = meta.get("title", "Untitled")
            parts = []
            for item in call.get("content", []):
                speaker = item.get("speakerName", "")
                text = " ".join(s.get("text", "") for s in item.get("sentences", []))
                if text:
                    parts.append(f"{speaker}: {text}")
            full = f"# {title}\n\n" + "\n".join(parts)
            filename = f"{meta.get('id', 'call')}.md"
            checksum = hashlib.sha256(full.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(full.encode())))
            self._cache[filename] = full
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()
