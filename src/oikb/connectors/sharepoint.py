"""SharePoint connector — sync a document library to a Knowledge Base.

Uses Microsoft Graph API. Auth via SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID,
SHAREPOINT_CLIENT_SECRET env vars (app-only auth).
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class SharePointConnector(BaseConnector):
    """Sync files from a SharePoint document library."""

    def __init__(
        self,
        site: str,
        library: str = "Documents",
        tenant_id: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.site = site
        self.library = library

        tid = tenant_id or os.environ.get("SHAREPOINT_TENANT_ID", "")
        cid = client_id or os.environ.get("SHAREPOINT_CLIENT_ID", "")
        secret = client_secret or os.environ.get("SHAREPOINT_CLIENT_SECRET", "")

        if not all([tid, cid, secret]):
            raise ValueError(
                "SharePoint credentials required. Set env vars:\n"
                "  SHAREPOINT_TENANT_ID, SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET"
            )

        # Get access token.
        token_resp = httpx.post(
            f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": secret,
                "scope": "https://graph.microsoft.com/.default",
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        self._http = httpx.Client(
            base_url="https://graph.microsoft.com/v1.0",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=60.0,
        )

        # Resolve site ID.
        site_resp = self._http.get(f"/sites/{self.site}")
        site_resp.raise_for_status()
        self._site_id = site_resp.json()["id"]

        # Resolve drive ID.
        drives_resp = self._http.get(f"/sites/{self._site_id}/drives")
        drives_resp.raise_for_status()
        self._drive_id = None
        for drive in drives_resp.json().get("value", []):
            if drive.get("name") == self.library:
                self._drive_id = drive["id"]
                break
        if not self._drive_id:
            drives = [d["name"] for d in drives_resp.json().get("value", [])]
            raise ValueError(f"Library '{self.library}' not found. Available: {drives}")

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        self._walk_folder("/", "", entries)
        entries.sort(key=lambda e: e.display_path)
        return entries

    def _walk_folder(self, folder_path: str, prefix: str, entries: list[ManifestEntry]) -> None:
        url = f"/drives/{self._drive_id}/root/children" if folder_path == "/" else f"/drives/{self._drive_id}/root:/{folder_path}:/children"
        resp = self._http.get(url)
        resp.raise_for_status()

        for item in resp.json().get("value", []):
            if "folder" in item:
                sub = f"{prefix}/{item['name']}" if prefix else item["name"]
                child_path = f"{folder_path}/{item['name']}" if folder_path != "/" else item["name"]
                self._walk_folder(child_path, sub, entries)
            elif "file" in item:
                etag = (item.get("eTag") or item.get("cTag", "")).strip('"')
                entries.append(ManifestEntry(
                    filename=item["name"],
                    path=prefix,
                    checksum=etag[:16] if etag else "",
                    size=item.get("size", 0),
                ))

    def read_file(self, path: str, filename: str) -> bytes:
        file_path = f"{path}/{filename}" if path else filename
        resp = self._http.get(f"/drives/{self._drive_id}/root:/{file_path}:/content")
        resp.raise_for_status()
        return resp.content

    def close(self) -> None:
        self._http.close()


def parse_sharepoint_source(source: str) -> dict[str, str | None]:
    """Parse sharepoint:site/library or sharepoint:site."""
    source = source.removeprefix("sharepoint:")
    parts = source.split("/", 1)
    site = parts[0]
    library = parts[1] if len(parts) > 1 else "Documents"
    if not site:
        raise ValueError("Invalid SharePoint source. Expected: sharepoint:<site>[/library]")
    return {"site": site, "library": library}
