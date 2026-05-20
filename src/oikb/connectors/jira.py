"""Jira connector — sync issues from a Jira project to a Knowledge Base.

Auth via JIRA_URL, JIRA_USER, JIRA_TOKEN env vars.
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class JiraConnector(BaseConnector):
    """Sync issues from a Jira project as text files."""

    def __init__(
        self,
        project_key: str,
        base_url: str | None = None,
        user: str | None = None,
        token: str | None = None,
    ):
        self.project_key = project_key
        self._base_url = (base_url or os.environ.get("JIRA_URL", "")).rstrip("/")
        self._user = user or os.environ.get("JIRA_USER", "")
        self._token = token or os.environ.get("JIRA_TOKEN", "")

        if not self._base_url:
            raise ValueError("Jira URL required. Set JIRA_URL env var.")
        if not self._token:
            raise ValueError("Jira API token required. Set JIRA_TOKEN env var.")

        self._http = httpx.Client(
            base_url=self._base_url,
            auth=(self._user, self._token) if self._user else None,
            headers={"Accept": "application/json"},
            timeout=30.0,
        )
        self._issue_cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        start = 0
        while True:
            resp = self._http.get(
                "/rest/api/3/search",
                params={"jql": f"project={self.project_key}", "startAt": start, "maxResults": 100,
                        "fields": "summary,description,status,updated,issuetype"},
            )
            resp.raise_for_status()
            data = resp.json()
            for issue in data.get("issues", []):
                key = issue["key"]
                fields = issue["fields"]
                updated = fields.get("updated", "")
                checksum = hashlib.sha256(f"{key}:{updated}".encode()).hexdigest()[:16]
                text = self._format_issue(issue)
                self._issue_cache[f"{key}.txt"] = text
                entries.append(ManifestEntry(filename=f"{key}.txt", path="", checksum=checksum, size=len(text.encode())))
            if start + len(data.get("issues", [])) >= data.get("total", 0):
                break
            start += len(data.get("issues", []))
        entries.sort(key=lambda e: e.display_path)
        return entries

    def _format_issue(self, issue: dict) -> str:
        fields = issue["fields"]
        key = issue["key"]
        summary = fields.get("summary", "")
        status = fields.get("status", {}).get("name", "")
        issue_type = fields.get("issuetype", {}).get("name", "")
        desc = self._adf_to_text(fields.get("description"))
        lines = [f"# [{key}] {summary}", f"Type: {issue_type}", f"Status: {status}", "", desc]
        return "\n".join(lines)

    def _adf_to_text(self, doc: dict | None) -> str:
        if not doc:
            return ""
        parts: list[str] = []
        for node in doc.get("content", []):
            if node.get("type") == "paragraph":
                text = "".join(c.get("text", "") for c in node.get("content", []) if c.get("type") == "text")
                parts.append(text)
            elif node.get("type") == "heading":
                text = "".join(c.get("text", "") for c in node.get("content", []) if c.get("type") == "text")
                level = node.get("attrs", {}).get("level", 2)
                parts.append(f"{'#' * level} {text}")
            elif node.get("type") == "codeBlock":
                text = "".join(c.get("text", "") for c in node.get("content", []) if c.get("type") == "text")
                parts.append(f"```\n{text}\n```")
        return "\n".join(parts)

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._issue_cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Issue not found: {filename}")
        return text.encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_jira_source(source: str) -> dict[str, str | None]:
    key = source.removeprefix("jira:")
    if not key:
        raise ValueError("Invalid Jira source. Expected: jira:<PROJECT_KEY>")
    return {"project_key": key}
