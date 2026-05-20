"""Airtable connector — sync records from an Airtable base to a Knowledge Base.

Auth via AIRTABLE_TOKEN env var (personal access token).
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class AirtableConnector(BaseConnector):
    """Sync records from an Airtable base/table."""

    def __init__(self, base_id: str, table_name: str = "Table 1", token: str | None = None):
        self.base_id = base_id
        self.table_name = table_name
        self._token = token or os.environ.get("AIRTABLE_TOKEN")
        if not self._token:
            raise ValueError("Airtable token required. Set AIRTABLE_TOKEN env var.")
        self._http = httpx.Client(
            base_url="https://api.airtable.com/v0",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        offset = None
        while True:
            params: dict[str, Any] = {}
            if offset:
                params["offset"] = offset
            resp = self._http.get(f"/{self.base_id}/{self.table_name}", params=params)
            resp.raise_for_status()
            data = resp.json()
            for record in data.get("records", []):
                rid = record["id"]
                fields = record.get("fields", {})
                text_lines = [f"{k}: {v}" for k, v in fields.items()]
                text = "\n".join(text_lines)
                name = str(fields.get("Name", fields.get("Title", rid)))
                filename = f"{re.sub(r'[^a-zA-Z0-9_-]', '_', name[:50])}.txt"
                checksum = hashlib.sha256(f"{rid}:{record.get('createdTime', '')}".encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
            offset = data.get("offset")
            if not offset:
                break
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Record not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_airtable_source(source: str) -> dict[str, str | None]:
    """Parse airtable:base-id or airtable:base-id/table-name."""
    source = source.removeprefix("airtable:")
    parts = source.split("/", 1)
    base_id = parts[0]
    table_name = parts[1] if len(parts) > 1 else "Table 1"
    if not base_id:
        raise ValueError("Invalid Airtable source. Expected: airtable:<base-id>[/table-name]")
    return {"base_id": base_id, "table_name": table_name}
