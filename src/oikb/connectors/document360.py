"""Document360 connector -- sync articles from a Document360 project."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class Document360Connector(BaseConnector):
    """Sync articles from Document360."""

    def __init__(self, project_id: str, token: str | None = None):
        self.project_id = project_id
        self._token = token or os.environ.get("DOCUMENT360_TOKEN")
        if not self._token:
            raise ValueError("Set DOCUMENT360_TOKEN env var.")
        self._http = httpx.Client(
            base_url="https://apihub.document360.io/v2",
            headers={"api_token": self._token},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        resp = self._http.get("/articles", params={"project_version_id": self.project_id})
        resp.raise_for_status()
        for article in resp.json().get("data", []):
            title = article.get("title", "untitled")
            body = article.get("html_content", "") or article.get("content", "")
            text = f"# {title}\n\n{body}"
            filename = f"{article['id']}.md"
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_document360_source(source: str) -> dict[str, str]:
    project_id = source.removeprefix("document360:")
    if not project_id:
        raise ValueError("Expected: document360:<project-version-id>")
    return {"project_id": project_id}
