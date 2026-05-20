"""DokuWiki connector -- sync pages via XML-RPC API."""

from __future__ import annotations

import hashlib
import os
import xmlrpc.client

from oikb.connectors import BaseConnector, ManifestEntry


class DokuWikiConnector(BaseConnector):
    """Sync pages from a DokuWiki instance via XML-RPC."""

    def __init__(self, base_url: str | None = None, namespace: str | None = None,
                 user: str | None = None, password: str | None = None):
        self._base = base_url or os.environ.get("DOKUWIKI_URL", "")
        self._user = user or os.environ.get("DOKUWIKI_USER", "")
        self._password = password or os.environ.get("DOKUWIKI_PASSWORD", "")
        if not self._base:
            raise ValueError("Set DOKUWIKI_URL env var.")
        self._namespace = namespace or ""
        self._rpc = xmlrpc.client.ServerProxy(f"{self._base.rstrip('/')}/lib/exe/xmlrpc.php")
        if self._user and self._password:
            self._rpc = xmlrpc.client.ServerProxy(
                f"{self._base.rstrip('/')}/lib/exe/xmlrpc.php",
                transport=None,
            )
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        try:
            if self._user:
                self._rpc.dokuwiki.login(self._user, self._password)
            pages = self._rpc.dokuwiki.getPagelist(self._namespace, {})
        except Exception:
            pages = self._rpc.wiki.getAllPages()

        entries: list[ManifestEntry] = []
        for page in pages:
            page_id = page.get("id", "")
            try:
                content = self._rpc.wiki.getPage(page_id)
            except Exception:
                continue
            if not content:
                continue
            checksum = hashlib.sha256(content.encode()).hexdigest()[:16]
            parts = page_id.rsplit(":", 1)
            path = parts[0].replace(":", "/") if len(parts) > 1 else ""
            filename = f"{parts[-1]}.txt"
            entries.append(ManifestEntry(filename=filename, path=path, checksum=checksum, size=len(content.encode())))
            self._cache[f"{path}/{filename}" if path else filename] = content
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        key = f"{path}/{filename}" if path else filename
        return (self._cache.get(key) or "").encode("utf-8")

    def close(self) -> None:
        pass


def parse_dokuwiki_source(source: str) -> dict[str, str | None]:
    namespace = source.removeprefix("dokuwiki:") or None
    return {"namespace": namespace}
