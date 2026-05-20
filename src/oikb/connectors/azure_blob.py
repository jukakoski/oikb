"""Azure Blob Storage connector — sync a container/prefix to a Knowledge Base.

Requires: pip install oikb[azure]
Uses ETags as checksums.
"""

from __future__ import annotations

import os
from typing import Any

from oikb.connectors import BaseConnector, ManifestEntry


class AzureBlobConnector(BaseConnector):
    """Sync files from an Azure Blob Storage container.

    Args:
        container:         Container name.
        prefix:            Blob name prefix to scope to (e.g. "docs/").
        connection_string: Azure Storage connection string
                           (or AZURE_STORAGE_CONNECTION_STRING env var).
    """

    def __init__(
        self,
        container: str,
        prefix: str | None = None,
        connection_string: str | None = None,
    ):
        try:
            from azure.storage.blob import ContainerClient
        except ImportError:
            raise ImportError(
                "Azure Blob connector requires azure-storage-blob. "
                "Install with: pip install oikb[azure]"
            )

        self.container_name = container
        self.prefix = prefix.strip("/") + "/" if prefix else ""

        conn_str = connection_string or os.environ.get("AZURE_STORAGE_CONNECTION_STRING")
        if not conn_str:
            raise ValueError(
                "Azure connection string required. Set via:\n"
                "  export AZURE_STORAGE_CONNECTION_STRING=<connection_string>"
            )

        self._client = ContainerClient.from_connection_string(conn_str, container)

    def build_manifest(self) -> list[ManifestEntry]:
        """List blobs in the container/prefix and build a manifest.

        ETags are used as checksums.
        """
        entries: list[ManifestEntry] = []

        blobs = self._client.list_blobs(name_starts_with=self.prefix or None)

        for blob in blobs:
            name = blob.name

            # Skip "directory" markers.
            if name.endswith("/"):
                continue

            # Strip prefix to get relative path.
            relative = name[len(self.prefix) :] if self.prefix else name

            parts = relative.rsplit("/", 1)
            if len(parts) == 2:
                dir_path, filename = parts
            else:
                dir_path, filename = "", parts[0]

            # ETag comes quoted — strip quotes.
            etag = (blob.etag or "").strip('"')

            entries.append(
                ManifestEntry(
                    filename=filename,
                    path=dir_path,
                    checksum=etag,
                    size=blob.size or 0,
                )
            )

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Download a blob from Azure."""
        name = self.prefix
        if path:
            name += f"{path}/{filename}"
        else:
            name += filename

        return self._client.download_blob(name).readall()


def parse_azure_source(source: str) -> dict[str, str | None]:
    """Parse an az://container/prefix source string.

    Examples:
        az://my-container
        az://my-container/docs/engineering
    """
    source = source.removeprefix("az://")

    parts = source.split("/", 1)
    container = parts[0]
    prefix = parts[1] if len(parts) > 1 else None

    if not container:
        raise ValueError("Invalid Azure Blob source. Expected: az://container[/prefix]")

    return {"container": container, "prefix": prefix}
