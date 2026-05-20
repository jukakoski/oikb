"""Confluence connector — sync a Confluence space to a Knowledge Base.

Uses the Confluence Cloud REST API v2. Pages are exported as plain text.
Auth via CONFLUENCE_URL, CONFLUENCE_USER, CONFLUENCE_TOKEN env vars.
"""

from __future__ import annotations

import hashlib
import html
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


def _storage_to_text(storage_html: str) -> str:
    """Convert Confluence storage format (XHTML) to plain text."""
    # Strip all HTML tags.
    text = re.sub(r"<[^>]+>", " ", storage_html)
    text = html.unescape(text)
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


class ConfluenceConnector(BaseConnector):
    """Sync pages from a Confluence Cloud space.

    Args:
        space_key: Confluence space key (e.g. "ENG").
        base_url:  Confluence instance URL (or CONFLUENCE_URL env var).
        user:      Confluence user email (or CONFLUENCE_USER env var).
        token:     Confluence API token (or CONFLUENCE_TOKEN env var).
    """

    def __init__(
        self,
        space_key: str,
        base_url: str | None = None,
        user: str | None = None,
        token: str | None = None,
    ):
        self.space_key = space_key

        self._base_url = (base_url or os.environ.get("CONFLUENCE_URL", "")).rstrip("/")
        self._user = user or os.environ.get("CONFLUENCE_USER", "")
        self._token = token or os.environ.get("CONFLUENCE_TOKEN", "")

        if not self._base_url:
            raise ValueError(
                "Confluence URL required. Set via:\n"
                "  export CONFLUENCE_URL=https://company.atlassian.net"
            )
        if not self._token:
            raise ValueError(
                "Confluence API token required. Set via:\n"
                "  export CONFLUENCE_TOKEN=<api_token>"
            )

        self._http = httpx.Client(
            base_url=f"{self._base_url}/wiki",
            auth=(self._user, self._token) if self._user else None,
            headers={"Accept": "application/json"},
            timeout=60.0,
        )

        # Cache page content for read_file.
        self._page_cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        """List all pages in the space and build a manifest."""
        entries: list[ManifestEntry] = []
        cursor = None

        while True:
            params: dict[str, Any] = {"limit": 250}
            if cursor:
                params["cursor"] = cursor

            resp = self._http.get(
                f"/api/v2/spaces/{self.space_key}/pages",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                page_id = page["id"]
                title = page["title"]
                version = page.get("version", {}).get("number", 0)

                # Use version number as part of checksum.
                checksum = hashlib.sha256(
                    f"{page_id}:v{version}".encode()
                ).hexdigest()[:16]

                # Sanitize title for filename.
                filename = re.sub(r'[<>:"/\\|?*]', "_", title) + ".txt"

                entries.append(
                    ManifestEntry(
                        filename=filename,
                        path="",
                        checksum=checksum,
                        size=0,
                    )
                )

                # Store page ID for later retrieval.
                self._page_cache[filename] = page_id

            # Handle pagination.
            next_link = data.get("_links", {}).get("next")
            if not next_link:
                break
            # Extract cursor from next link.
            cursor_match = re.search(r"cursor=([^&]+)", next_link)
            cursor = cursor_match.group(1) if cursor_match else None
            if not cursor:
                break

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Fetch a page's content and return as text."""
        page_id = self._page_cache.get(filename)
        if not page_id:
            raise FileNotFoundError(f"Page not found: {filename}")

        resp = self._http.get(
            f"/api/v2/pages/{page_id}",
            params={"body-format": "storage"},
        )
        resp.raise_for_status()
        data = resp.json()

        storage = data.get("body", {}).get("storage", {}).get("value", "")
        text = _storage_to_text(storage)
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_confluence_source(source: str) -> dict[str, str | None]:
    """Parse a confluence:SPACEKEY source string.

    Examples:
        confluence:ENG
        confluence:https://company.atlassian.net/ENG
    """
    source = source.removeprefix("confluence:")

    # Check if it includes a URL.
    if source.startswith("https://"):
        parts = source.rsplit("/", 1)
        if len(parts) == 2:
            return {"base_url": parts[0], "space_key": parts[1]}
        raise ValueError("Invalid Confluence source. Expected: confluence:SPACEKEY")

    return {"space_key": source, "base_url": None}
