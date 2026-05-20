"""Google Cloud Storage connector — sync a GCS bucket/prefix to a Knowledge Base.

Requires: pip install oikb[gcs]
Uses MD5 hashes as checksums — GCS computes these server-side.
"""

from __future__ import annotations

from typing import Any

from oikb.connectors import BaseConnector, ManifestEntry


class GCSConnector(BaseConnector):
    """Sync files from a Google Cloud Storage bucket.

    Args:
        bucket: GCS bucket name.
        prefix: Key prefix to scope to (e.g. "docs/").
    """

    def __init__(
        self,
        bucket: str,
        prefix: str | None = None,
    ):
        try:
            from google.cloud import storage
        except ImportError:
            raise ImportError(
                "GCS connector requires google-cloud-storage. "
                "Install with: pip install oikb[gcs]"
            )

        self.bucket_name = bucket
        self.prefix = prefix.strip("/") + "/" if prefix else ""

        client = storage.Client()
        self._bucket = client.bucket(bucket)

    def build_manifest(self) -> list[ManifestEntry]:
        """List objects in the bucket/prefix and build a manifest.

        MD5 hashes are used as checksums.
        """
        entries: list[ManifestEntry] = []

        blobs = self._bucket.list_blobs(prefix=self.prefix or None)

        for blob in blobs:
            key = blob.name

            # Skip "directory" markers.
            if key.endswith("/"):
                continue

            # Strip prefix to get relative path.
            relative = key[len(self.prefix) :] if self.prefix else key

            parts = relative.rsplit("/", 1)
            if len(parts) == 2:
                dir_path, filename = parts
            else:
                dir_path, filename = "", parts[0]

            entries.append(
                ManifestEntry(
                    filename=filename,
                    path=dir_path,
                    checksum=blob.md5_hash or blob.etag or "",
                    size=blob.size or 0,
                )
            )

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Download an object from GCS."""
        key = self.prefix
        if path:
            key += f"{path}/{filename}"
        else:
            key += filename

        blob = self._bucket.blob(key)
        return blob.download_as_bytes()


def parse_gcs_source(source: str) -> dict[str, str | None]:
    """Parse a gs://bucket/prefix source string.

    Examples:
        gs://my-bucket
        gs://my-bucket/docs/engineering
    """
    source = source.removeprefix("gs://")

    parts = source.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else None

    if not bucket:
        raise ValueError("Invalid GCS source. Expected: gs://bucket[/prefix]")

    return {"bucket": bucket, "prefix": prefix}
