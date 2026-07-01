"""Confluence connector — sync a Confluence space to a Knowledge Base.

Uses the Confluence Cloud REST API v2. Pages are exported as plain text or Markdown.
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


_OUTPUT_FORMATS = {"text", "markdown"}
_BODY_FORMATS = {
    "storage",
    "atlas_doc_format",
    "view",
    "export_view",
    "anonymous_export_view",
    "styled_view",
    "editor",
}


def _storage_to_text(storage_html: str) -> str:
    """Convert Confluence storage format (XHTML) to plain text."""
    # Strip all HTML tags.
    text = re.sub(r"<[^>]+>", " ", storage_html)
    text = html.unescape(text)
    # Collapse whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _html_to_markdown(value: str) -> str:
    """Convert Confluence-rendered HTML to Markdown."""
    try:
        from markdownify import markdownify as md
    except ImportError as exc:
        raise RuntimeError(
            "Markdown output requires the 'markdownify' package. "
            "Install it or use output_format='text'."
        ) from exc

    text = md(value, heading_style="ATX", bullets="-")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


class ConfluenceConnector(BaseConnector):
    """Sync pages from a Confluence Cloud space.

    Args:
        space_key: Confluence space key (e.g. "ENG").
        base_url:  Confluence instance URL (or CONFLUENCE_URL env var).
        user:      Confluence user email (or CONFLUENCE_USER env var).
        token:     Confluence API token (or CONFLUENCE_TOKEN env var).
        output_format: Output format: "text" or "markdown". Defaults to "text".
        body_format: Confluence body format. Defaults to "storage" for text and
            "export_view" for markdown.
    """

    def __init__(
        self,
        space_key: str,
        base_url: str | None = None,
        user: str | None = None,
        token: str | None = None,
        output_format: str = "text",
        body_format: str | None = None,
    ):
        if output_format not in _OUTPUT_FORMATS:
            raise ValueError(
                f"Invalid output_format: {output_format}. "
                f"Expected one of: {', '.join(sorted(_OUTPUT_FORMATS))}"
            )
        if body_format is None:
            body_format = "export_view" if output_format == "markdown" else "storage"
        if body_format not in _BODY_FORMATS:
            raise ValueError(
                f"Invalid body_format: {body_format}. "
                f"Expected one of: {', '.join(sorted(_BODY_FORMATS))}"
            )

        self.space_key = space_key
        self.output_format = output_format
        self.body_format = body_format

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
                extension = ".md" if self.output_format == "markdown" else ".txt"
                filename = re.sub(r'[<>:"/\\|?*]', "_", title) + extension

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
            params={"body-format": self.body_format},
        )
        resp.raise_for_status()
        data = resp.json()

        body = data.get("body", {})
        value = body.get(self.body_format, {}).get("value", "")
        if self.output_format == "markdown":
            text = _html_to_markdown(value)
        else:
            text = _storage_to_text(value)
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
