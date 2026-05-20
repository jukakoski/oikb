"""Salesforce connector — sync knowledge articles from Salesforce.

Auth via SALESFORCE_URL, SALESFORCE_TOKEN env vars.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class SalesforceConnector(BaseConnector):
    """Sync Knowledge articles from Salesforce."""

    def __init__(self, instance_url: str | None = None, token: str | None = None):
        self._url = (instance_url or os.environ.get("SALESFORCE_URL", "")).rstrip("/")
        self._token = token or os.environ.get("SALESFORCE_TOKEN")
        if not self._url or not self._token:
            raise ValueError("Salesforce credentials required. Set SALESFORCE_URL and SALESFORCE_TOKEN env vars.")
        self._http = httpx.Client(
            base_url=self._url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        query = "SELECT Id, Title, ArticleBody, LastModifiedDate FROM KnowledgeArticleVersion WHERE PublishStatus='Online' AND Language='en_US'"
        url = f"/services/data/v59.0/query?q={query}"
        while url:
            resp = self._http.get(url)
            resp.raise_for_status()
            data = resp.json()
            for record in data.get("records", []):
                title = re.sub(r'[<>:"/\\|?*]', "_", record.get("Title", "Untitled"))
                body = re.sub(r"<[^>]+>", " ", record.get("ArticleBody", "") or "")
                text = f"# {title}\n\n{body}"
                filename = f"{record['Id']}_{title[:50]}.txt"
                checksum = hashlib.sha256(f"{record['Id']}:{record.get('LastModifiedDate', '')}".encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
            url = data.get("nextRecordsUrl")
        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Article not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_salesforce_source(source: str) -> dict[str, str | None]:
    # salesforce: (no args, uses env vars)
    return {}
