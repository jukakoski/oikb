"""Bitbucket connector — sync a Bitbucket repo to a Knowledge Base.

Uses the Bitbucket Cloud REST API 2.0.
Auth via BITBUCKET_USER + BITBUCKET_APP_PASSWORD env vars.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class BitbucketConnector(BaseConnector):
    """Sync files from a Bitbucket repository."""

    def __init__(self, owner: str, repo: str, branch: str | None = None, path: str | None = None,
                 user: str | None = None, app_password: str | None = None):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.path = path.strip("/") if path else None

        u = user or os.environ.get("BITBUCKET_USER", "")
        p = app_password or os.environ.get("BITBUCKET_APP_PASSWORD", "")

        self._http = httpx.Client(
            base_url="https://api.bitbucket.org/2.0",
            auth=(u, p) if u and p else None,
            timeout=60.0,
        )

    def build_manifest(self) -> list[ManifestEntry]:
        ref = self.branch or self._get_default_branch()
        entries: list[ManifestEntry] = []
        src_path = self.path or ""
        url = f"/repositories/{self.owner}/{self.repo}/src/{ref}/{src_path}"

        self._walk(url, ref, "", entries)
        entries.sort(key=lambda e: e.display_path)
        return entries

    def _walk(self, url: str, ref: str, prefix: str, entries: list[ManifestEntry]) -> None:
        while url:
            resp = self._http.get(url)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("values", []):
                if item["type"] == "commit_directory":
                    name = item["path"].split("/")[-1]
                    sub = f"{prefix}/{name}" if prefix else name
                    self._walk(item["links"]["self"]["href"].replace("https://api.bitbucket.org/2.0", ""), ref, sub, entries)
                elif item["type"] == "commit_file":
                    name = item["path"].split("/")[-1]
                    entries.append(ManifestEntry(
                        filename=name, path=prefix,
                        checksum=item.get("commit", {}).get("hash", "")[:16],
                        size=item.get("size", 0),
                    ))
            url = data.get("next", "").replace("https://api.bitbucket.org/2.0", "") if data.get("next") else None

    def read_file(self, path: str, filename: str) -> bytes:
        ref = self.branch or self._get_default_branch()
        file_path = f"{path}/{filename}" if path else filename
        if self.path:
            file_path = f"{self.path}/{file_path}"
        resp = self._http.get(f"/repositories/{self.owner}/{self.repo}/src/{ref}/{file_path}")
        resp.raise_for_status()
        return resp.content

    def _get_default_branch(self) -> str:
        resp = self._http.get(f"/repositories/{self.owner}/{self.repo}")
        resp.raise_for_status()
        return resp.json().get("mainbranch", {}).get("name", "main")

    def close(self) -> None:
        self._http.close()


def parse_bitbucket_source(source: str) -> dict[str, str | None]:
    source = source.removeprefix("bitbucket:")
    parts = source.split("/", 2)
    if len(parts) < 2:
        raise ValueError("Invalid Bitbucket source. Expected: bitbucket:owner/repo")
    return {"owner": parts[0], "repo": parts[1], "path": parts[2] if len(parts) > 2 else None}
