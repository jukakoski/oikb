"""Egnyte connector -- sync files from an Egnyte domain."""

from __future__ import annotations

import hashlib
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class EgnyteConnector(BaseConnector):
    """Sync files from Egnyte."""

    def __init__(self, path: str = "/", token: str | None = None, domain: str | None = None):
        self._token = token or os.environ.get("EGNYTE_TOKEN")
        self._domain = domain or os.environ.get("EGNYTE_DOMAIN")
        if not self._token or not self._domain:
            raise ValueError("Set EGNYTE_DOMAIN and EGNYTE_TOKEN env vars.")
        self._path = path.rstrip("/")
        self._http = httpx.Client(
            base_url=f"https://{self._domain}.egnyte.com/pubapi/v1",
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=30.0,
        )

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        self._walk(self._path, "", entries)
        return entries

    def _walk(self, api_path: str, prefix: str, entries: list[ManifestEntry]) -> None:
        resp = self._http.get(f"/fs{api_path}")
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("files", []):
            checksum = item.get("checksum", "") or hashlib.sha256(item["name"].encode()).hexdigest()[:16]
            entries.append(ManifestEntry(
                filename=item["name"], path=prefix,
                checksum=checksum[:16], size=item.get("size", 0),
            ))
        for folder in data.get("folders", []):
            sub = f"{api_path}/{folder['name']}"
            sub_prefix = f"{prefix}/{folder['name']}" if prefix else folder["name"]
            self._walk(sub, sub_prefix, entries)

    def read_file(self, path: str, filename: str) -> bytes:
        api_path = f"{self._path}/{path}/{filename}" if path else f"{self._path}/{filename}"
        resp = self._http.get(f"/fs-content{api_path}")
        resp.raise_for_status()
        return resp.content

    def close(self) -> None:
        self._http.close()


def parse_egnyte_source(source: str) -> dict[str, str]:
    path = source.removeprefix("egnyte:") or "/"
    return {"path": path}
