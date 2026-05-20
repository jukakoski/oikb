"""S3 connector — sync an S3 bucket/prefix to a Knowledge Base.

Requires: pip install oikb[s3]
Uses ETags as checksums — S3 computes these server-side.
"""

from __future__ import annotations

from typing import Any

from oikb.connectors import BaseConnector, ManifestEntry


class S3Connector(BaseConnector):
    """Sync files from an S3 bucket.

    Args:
        bucket: S3 bucket name.
        prefix: Key prefix to scope to (e.g. "docs/").
        region: AWS region (default: from boto3 config).
    """

    def __init__(
        self,
        bucket: str,
        prefix: str | None = None,
        region: str | None = None,
    ):
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "S3 connector requires boto3. Install with: pip install oikb[s3]"
            )

        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix else ""

        session_kwargs: dict[str, Any] = {}
        if region:
            session_kwargs["region_name"] = region

        self._s3 = boto3.client("s3", **session_kwargs)

    def build_manifest(self) -> list[ManifestEntry]:
        """List objects in the bucket/prefix and build a manifest.

        ETags are used as checksums — they're MD5 hashes for single-part uploads,
        and composite hashes for multipart. Good enough for change detection.
        """
        entries: list[ManifestEntry] = []
        paginator = self._s3.get_paginator("list_objects_v2")

        page_kwargs: dict[str, Any] = {"Bucket": self.bucket}
        if self.prefix:
            page_kwargs["Prefix"] = self.prefix

        for page in paginator.paginate(**page_kwargs):
            for obj in page.get("Contents", []):
                key = obj["Key"]

                # Skip "directory" markers.
                if key.endswith("/"):
                    continue

                # Strip prefix to get relative path.
                relative = key[len(self.prefix):] if self.prefix else key

                parts = relative.rsplit("/", 1)
                if len(parts) == 2:
                    dir_path, filename = parts
                else:
                    dir_path, filename = "", parts[0]

                # ETag comes quoted from S3 — strip quotes.
                etag = obj["ETag"].strip('"')

                entries.append(
                    ManifestEntry(
                        filename=filename,
                        path=dir_path,
                        checksum=etag,
                        size=obj["Size"],
                    )
                )

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Download an object from S3."""
        key = self.prefix
        if path:
            key += f"{path}/{filename}"
        else:
            key += filename

        resp = self._s3.get_object(Bucket=self.bucket, Key=key)
        return resp["Body"].read()


def parse_s3_source(source: str) -> dict[str, str | None]:
    """Parse an s3://bucket/prefix source string.

    Examples:
        s3://my-bucket
        s3://my-bucket/docs/engineering
    """
    source = source.removeprefix("s3://")

    parts = source.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else None

    if not bucket:
        raise ValueError(f"Invalid S3 source. Expected: s3://bucket[/prefix]")

    return {"bucket": bucket, "prefix": prefix}
