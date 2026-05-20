"""GitLab connector — sync a GitLab repo to a Knowledge Base via the API.

Requires: pip install oikb[gitlab]  (uses httpx, already a core dep)
Uses the GitLab Repository Tree API — no local clone needed.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class GitLabConnector(BaseConnector):
    """Sync files from a GitLab repository.

    Args:
        owner:    Project namespace (e.g. "open-webui").
        repo:     Project name (e.g. "docs").
        branch:   Branch to sync from (default: project default branch).
        path:     Subdirectory to scope to (e.g. "docs/").
        token:    GitLab personal access token (or GITLAB_TOKEN env var).
        base_url: GitLab instance URL (default: https://gitlab.com).
    """

    def __init__(
        self,
        owner: str,
        repo: str,
        branch: str | None = None,
        path: str | None = None,
        token: str | None = None,
        base_url: str | None = None,
    ):
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.path = path.strip("/") if path else None
        self._token = token or os.environ.get("GITLAB_TOKEN")
        self._base_url = (base_url or os.environ.get("GITLAB_URL", "https://gitlab.com")).rstrip("/")

        headers: dict[str, str] = {}
        if self._token:
            headers["PRIVATE-TOKEN"] = self._token

        self._http = httpx.Client(
            base_url=f"{self._base_url}/api/v4",
            headers=headers,
            timeout=60.0,
        )

        # URL-encode the project path for GitLab's API.
        self._project_id = f"{self.owner}%2F{self.repo}"

    def build_manifest(self) -> list[ManifestEntry]:
        """Fetch the repo tree and build a manifest.

        Uses the recursive tree API. Blob IDs are content-addressable hashes.
        """
        ref = self.branch or self._get_default_branch()
        entries: list[ManifestEntry] = []

        # GitLab paginates the tree endpoint.
        page = 1
        while True:
            resp = self._http.get(
                f"/projects/{self._project_id}/repository/tree",
                params={
                    "ref": ref,
                    "recursive": "true",
                    "per_page": 100,
                    "page": page,
                    "path": self.path or "",
                },
            )
            resp.raise_for_status()
            items = resp.json()

            if not items:
                break

            for item in items:
                if item["type"] != "blob":
                    continue

                file_path = item["path"]

                # Strip prefix if scoped to a subdirectory.
                if self.path:
                    if not file_path.startswith(self.path + "/"):
                        continue
                    file_path = file_path[len(self.path) + 1 :]

                parts = file_path.rsplit("/", 1)
                if len(parts) == 2:
                    dir_path, filename = parts
                else:
                    dir_path, filename = "", parts[0]

                entries.append(
                    ManifestEntry(
                        filename=filename,
                        path=dir_path,
                        checksum=item["id"],  # Git blob SHA.
                        size=0,  # Tree endpoint doesn't return size.
                    )
                )

            page += 1

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Download a file's raw content via the GitLab Repository Files API."""
        import urllib.parse

        file_path = f"{path}/{filename}" if path else filename
        if self.path:
            file_path = f"{self.path}/{file_path}"

        encoded_path = urllib.parse.quote(file_path, safe="")
        ref = self.branch or self._get_default_branch()

        resp = self._http.get(
            f"/projects/{self._project_id}/repository/files/{encoded_path}/raw",
            params={"ref": ref},
        )
        resp.raise_for_status()
        return resp.content

    def _get_default_branch(self) -> str:
        """Fetch the project's default branch name."""
        resp = self._http.get(f"/projects/{self._project_id}")
        resp.raise_for_status()
        return resp.json()["default_branch"]

    def close(self) -> None:
        self._http.close()


def parse_gitlab_source(source: str) -> dict[str, str | None]:
    """Parse a gitlab:owner/repo[/path] source string.

    Examples:
        gitlab:open-webui/docs
        gitlab:open-webui/docs/api
    """
    source = source.removeprefix("gitlab:")

    parts = source.split("/", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid GitLab source: {source}. Expected: gitlab:owner/repo")

    owner = parts[0]
    repo = parts[1]
    path = parts[2] if len(parts) > 2 else None

    return {"owner": owner, "repo": repo, "path": path}
