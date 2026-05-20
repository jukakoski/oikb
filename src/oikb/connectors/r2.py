"""Cloudflare R2 connector — S3-compatible storage.

Uses boto3 with custom endpoint. Auth via R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID env vars.
"""

from __future__ import annotations

import os
from typing import Any

from oikb.connectors.s3 import S3Connector


class R2Connector(S3Connector):
    """Sync files from Cloudflare R2 (S3-compatible)."""

    def __init__(self, bucket: str, prefix: str | None = None, account_id: str | None = None):
        try:
            import boto3
        except ImportError:
            raise ImportError("R2 connector requires boto3. Install with: pip install oikb[s3]")

        self.bucket = bucket
        self.prefix = prefix.strip("/") + "/" if prefix else ""

        aid = account_id or os.environ.get("R2_ACCOUNT_ID", "")
        key_id = os.environ.get("R2_ACCESS_KEY_ID", "")
        secret = os.environ.get("R2_SECRET_ACCESS_KEY", "")

        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{aid}.r2.cloudflarestorage.com",
            aws_access_key_id=key_id,
            aws_secret_access_key=secret,
        )


def parse_r2_source(source: str) -> dict[str, str | None]:
    source = source.removeprefix("r2://")
    parts = source.split("/", 1)
    return {"bucket": parts[0], "prefix": parts[1] if len(parts) > 1 else None}
