"""ClickUp connector — sync tasks from a ClickUp space.

Auth via CLICKUP_TOKEN env var.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class ClickUpConnector(BaseConnector):
    def __init__(self, space_id: str, token: str | None = None):
        self.space_id = space_id
        self._token = token or os.environ.get("CLICKUP_TOKEN")
        if not self._token:
            raise ValueError("ClickUp token required. Set CLICKUP_TOKEN env var.")
        self._http = httpx.Client(base_url="https://api.clickup.com/api/v2", headers={"Authorization": self._token}, timeout=30.0)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        # Get lists in space, then tasks in each list.
        folders = self._http.get(f"/space/{self.space_id}/folder").json().get("folders", [])
        list_ids: list[str] = []
        for folder in folders:
            for lst in folder.get("lists", []):
                list_ids.append(lst["id"])
        # Also folderless lists.
        fl = self._http.get(f"/space/{self.space_id}/list").json().get("lists", [])
        list_ids.extend(l["id"] for l in fl)

        for lid in list_ids:
            page = 0
            while True:
                resp = self._http.get(f"/list/{lid}/task", params={"page": page})
                resp.raise_for_status()
                tasks = resp.json().get("tasks", [])
                if not tasks:
                    break
                for task in tasks:
                    title = re.sub(r'[<>:"/\\|?*]', "_", task.get("name", "Untitled"))
                    text = f"# {title}\nStatus: {task.get('status', {}).get('status', '')}\n\n{task.get('text_content', '') or ''}"
                    filename = f"{task['id']}_{title[:50]}.txt"
                    checksum = hashlib.sha256(f"{task['id']}:{task.get('date_updated', '')}".encode()).hexdigest()[:16]
                    entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                    self._cache[filename] = text
                page += 1
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_clickup_source(source: str) -> dict[str, str | None]:
    sid = source.removeprefix("clickup:")
    if not sid:
        raise ValueError("Expected: clickup:<space-id>")
    return {"space_id": sid}
