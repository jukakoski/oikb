"""Oracle Cloud Storage connector -- sync objects from an OCI bucket."""

from __future__ import annotations

import hashlib
import os

from oikb.connectors import BaseConnector, ManifestEntry


class OracleStorageConnector(BaseConnector):
    """Sync files from Oracle Cloud Infrastructure Object Storage."""

    def __init__(self, bucket: str, prefix: str | None = None,
                 namespace: str | None = None):
        try:
            import oci
        except ImportError:
            raise ImportError("pip install oci")

        self.bucket = bucket
        self.prefix = prefix or ""
        self._namespace = namespace or os.environ.get("OCI_NAMESPACE", "")
        config = oci.config.from_file()
        if not self._namespace:
            self._namespace = oci.ObjectStorageClient(config).get_namespace().data
        self._client = oci.ObjectStorageClient(config)

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        next_start = None
        while True:
            kwargs = {"namespace_name": self._namespace, "bucket_name": self.bucket}
            if self.prefix:
                kwargs["prefix"] = self.prefix
            if next_start:
                kwargs["start"] = next_start
            resp = self._client.list_objects(**kwargs)
            for obj in resp.data.objects:
                key = obj.name
                parts = key.rsplit("/", 1)
                path = parts[0] if len(parts) > 1 else ""
                filename = parts[-1]
                if not filename:
                    continue
                checksum = obj.md5 or hashlib.sha256(key.encode()).hexdigest()[:16]
                entries.append(ManifestEntry(
                    filename=filename, path=path, checksum=checksum[:16], size=obj.size or 0,
                ))
            next_start = resp.data.next_start_with
            if not next_start:
                break
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        key = f"{path}/{filename}" if path else filename
        resp = self._client.get_object(self._namespace, self.bucket, key)
        return resp.data.content

    def close(self) -> None:
        pass


def parse_oracle_source(source: str) -> dict[str, str | None]:
    source = source.removeprefix("oci://")
    parts = source.split("/", 1)
    return {"bucket": parts[0], "prefix": parts[1] if len(parts) > 1 else None}
