"""GitHub connector — sync a GitHub repo to a Knowledge Base via the API.

Requires: pip install oikb[github]
Uses the GitHub Trees API for checksums (blob SHAs) — no local clone needed.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class GitHubConnector(BaseConnector):
    """Sync files from a GitHub repository.

    Args:
        owner:  Repository owner (e.g. "open-webui").
        repo:   Repository name (e.g. "docs").
        branch: Branch to sync from (default: repo default branch).
        path:   Subdirectory to scope to (e.g. "docs/").
        token:  GitHub personal access token (or GITHUB_TOKEN env var).
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        branch: str | None = None,
        path: str | None = None,
        token: str | None = None,
    ):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.path = path.strip("/") if path else None
        self._token = token or os.environ.get("GITHUB_TOKEN")
        self._default_branch: str | None = None

        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        self._http = httpx.Client(
            base_url="https://api.github.com",
            headers=headers,
            timeout=60.0,
        )

    def build_manifest(self) -> list[ManifestEntry]:
        """Fetch the repo tree and build a manifest.

        Uses the recursive tree API — one request for the full repo structure.
        Blob SHAs are used as checksums (they're content-addressable hashes).
        """
        ref = self.branch or self._get_default_branch()

        # Get recursive tree.
        resp = self._http.get(
            f"/repos/{self.owner}/{self.repo}/git/trees/{ref}",
            params={"recursive": "1"},
        )
        resp.raise_for_status()
        tree = resp.json()

        entries: list[ManifestEntry] = []

        for item in tree.get("tree", []):
            if item["type"] != "blob":
                continue

            file_path = item["path"]

            # Filter by path prefix if specified.
            if self.path:
                if not file_path.startswith(self.path + "/"):
                    continue
                # Strip the prefix so paths are relative to the scoped dir.
                file_path = file_path[len(self.path) + 1:]

            parts = file_path.rsplit("/", 1)
            if len(parts) == 2:
                dir_path, filename = parts
            else:
                dir_path, filename = "", parts[0]

            entries.append(
                ManifestEntry(
                    filename=filename,
                    path=dir_path,
                    checksum=item["sha"],  # Git blob SHA — content-addressable.
                    size=item.get("size", 0),
                )
            )

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Download a file's content via the GitHub Contents API."""
        file_path = f"{path}/{filename}" if path else filename

        if self.path:
            file_path = f"{self.path}/{file_path}"

        ref = self.branch or self._get_default_branch()

        resp = self._http.get(
            f"/repos/{self.owner}/{self.repo}/contents/{file_path}",
            params={"ref": ref},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        resp.raise_for_status()
        return resp.content

    def _get_default_branch(self) -> str:
        """Fetch and cache the repo's default branch name."""
        if self._default_branch is None:
            resp = self._http.get(f"/repos/{self.owner}/{self.repo}")
            resp.raise_for_status()
            self._default_branch = resp.json()["default_branch"]
        return self._default_branch

    def close(self) -> None:
        self._http.close()


def parse_github_source(source: str) -> dict[str, str | None]:
    """Parse a github:owner/repo[/path] source string.

    Examples:
        github:open-webui/docs
        github:open-webui/docs/api
        github:owner/repo --branch main --path docs/
    """
    # Strip "github:" prefix.
    source = source.removeprefix("github:")

    parts = source.split("/", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub source: {source}. Expected: github:owner/repo")

    owner = parts[0]
    repo = parts[1]
    path = parts[2] if len(parts) > 2 else None

    return {"owner": owner, "repo": repo, "path": path}
