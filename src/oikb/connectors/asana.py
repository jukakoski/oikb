"""Asana connector — sync tasks from an Asana project.

Auth via ASANA_TOKEN env var (personal access token).
"""

from __future__ import annotations

import hashlib
import os
import re

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class AsanaConnector(BaseConnector):
    def __init__(self, project_id: str, token: str | None = None):
        self.project_id = project_id
        self._token = token or os.environ.get("ASANA_TOKEN")
        if not self._token:
            raise ValueError("Asana token required. Set ASANA_TOKEN env var.")
        self._http = httpx.Client(base_url="https://app.asana.com/api/1.0", headers={"Authorization": f"Bearer {self._token}"}, timeout=30.0)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        resp = self._http.get(f"/projects/{self.project_id}/tasks", params={"opt_fields": "name,notes,modified_at,completed"})
        resp.raise_for_status()
        for task in resp.json().get("data", []):
            title = re.sub(r'[<>:"/\\|?*]', "_", task.get("name", "Untitled"))
            text = f"# {title}\nCompleted: {task.get('completed', False)}\n\n{task.get('notes', '')}"
            filename = f"{task['gid']}_{title[:50]}.txt"
            checksum = hashlib.sha256(f"{task['gid']}:{task.get('modified_at', '')}".encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_asana_source(source: str) -> dict[str, str | None]:
    pid = source.removeprefix("asana:")
    if not pid:
        raise ValueError("Expected: asana:<project-id>")
    return {"project_id": pid}
