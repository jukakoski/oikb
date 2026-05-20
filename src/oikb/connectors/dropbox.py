"""Dropbox connector — sync a Dropbox folder to a Knowledge Base.

Requires: pip install oikb[dropbox]
Uses Dropbox content_hash as checksums.
"""

from __future__ import annotations

import os

from oikb.connectors import BaseConnector, ManifestEntry


class DropboxConnector(BaseConnector):
    """Sync files from a Dropbox folder.

    Args:
        path:  Folder path in Dropbox (e.g. "/docs").
        token: Dropbox access token (or DROPBOX_TOKEN env var).
    """

    def __init__(
        self,
        path: str,
        token: str | None = None,
    ):
        try:
            import dropbox as dbx
        except ImportError:
            raise ImportError(
                "Dropbox connector requires the dropbox package. "
                "Install with: pip install oikb[dropbox]"
            )

        self._path = path.rstrip("/")
        if not self._path.startswith("/"):
            self._path = f"/{self._path}"

        access_token = token or os.environ.get("DROPBOX_TOKEN")
        if not access_token:
            raise ValueError(
                "Dropbox access token required. Set via:\n"
                "  export DROPBOX_TOKEN=<access_token>"
            )

        self._dbx = dbx.Dropbox(access_token)

    def build_manifest(self) -> list[ManifestEntry]:
        """List files in the Dropbox folder recursively.

        content_hash is Dropbox's own content-addressable hash.
        """
        import dropbox as dbx

        entries: list[ManifestEntry] = []

        result = self._dbx.files_list_folder(self._path, recursive=True)

        while True:
            for entry in result.entries:
                if not isinstance(entry, dbx.files.FileMetadata):
                    continue

                # Get path relative to the sync root.
                relative = entry.path_display
                if relative.startswith(self._path):
                    relative = relative[len(self._path) :].lstrip("/")

                parts = relative.rsplit("/", 1)
                if len(parts) == 2:
                    dir_path, filename = parts
                else:
                    dir_path, filename = "", parts[0]

                entries.append(
                    ManifestEntry(
                        filename=filename,
                        path=dir_path,
                        checksum=entry.content_hash or "",
                        size=entry.size,
                    )
                )

            if not result.has_more:
                break
            result = self._dbx.files_list_folder_continue(result.cursor)

        entries.sort(key=lambda e: e.display_path)
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        """Download a file from Dropbox."""
        file_path = self._path
        if path:
            file_path += f"/{path}/{filename}"
        else:
            file_path += f"/{filename}"

        _, response = self._dbx.files_download(file_path)
        return response.content


def parse_dropbox_source(source: str) -> dict[str, str | None]:
    """Parse a dropbox:/path source string.

    Examples:
        dropbox:/docs
        dropbox:/team/engineering/wiki
    """
    path = source.removeprefix("dropbox:")

    if not path:
        raise ValueError("Invalid Dropbox source. Expected: dropbox:/path")

    return {"path": path}
