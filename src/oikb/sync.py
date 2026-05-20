"""Sync orchestrator — diff → cleanup → mkdir → upload."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import click

from oikb.client import OikbClient
from oikb.connectors import BaseConnector


@dataclass
class SyncResult:
    """Summary of a completed sync operation."""

    added: int = 0
    modified: int = 0
    deleted: int = 0
    unmodified: int = 0
    dirs_created: int = 0
    dirs_removed: int = 0
    errors: list[str] | None = None

    @property
    def total_changes(self) -> int:
        return self.added + self.modified + self.deleted

    def summary(self) -> str:
        parts = []
        if self.added:
            parts.append(f"{self.added} added")
        if self.modified:
            parts.append(f"{self.modified} modified")
        if self.deleted:
            parts.append(f"{self.deleted} deleted")
        if self.unmodified:
            parts.append(f"{self.unmodified} unchanged")
        if self.dirs_created:
            parts.append(f"{self.dirs_created} dirs created")
        if self.dirs_removed:
            parts.append(f"{self.dirs_removed} dirs removed")
        return ", ".join(parts) if parts else "nothing to do"


def run_sync(
    client: OikbClient,
    connector: BaseConnector,
    kb_id: str,
    dry_run: bool = False,
    verbose: bool = False,
    quiet: bool = False,
) -> SyncResult:
    """Execute a full incremental sync.

    Steps:
      1. Build manifest from connector
      2. POST manifest to /sync/diff
      3. Cleanup stale files (delete before upload)
      4. Create missing directories
      5. Upload added + modified files
      6. Return summary
    """
    result = SyncResult()
    result.errors = []

    # ── 1. Build manifest ──────────────────────────────────────
    if verbose:
        click.echo("Scanning source...", err=True)

    manifest = connector.build_manifest()

    if verbose:
        click.echo(f"  {len(manifest)} files found", err=True)

    if not manifest:
        if not quiet:
            click.echo("Source is empty — nothing to sync.", err=True)
        return result

    # ── 2. Compute diff ────────────────────────────────────────
    if verbose:
        click.echo("Computing diff...", err=True)

    diff = client.sync_diff(kb_id, [e.to_dict() for e in manifest])

    added: list[dict[str, Any]] = diff.get("added", [])
    modified: list[dict[str, Any]] = diff.get("modified", [])
    deleted: list[dict[str, Any]] = diff.get("deleted", [])
    unmodified_count: int = diff.get("unmodified_count", 0)
    mkdir: list[str] = diff.get("mkdir", [])
    rmdir: list[str] = diff.get("rmdir", [])
    directory_map: dict[str, str] = diff.get("directory_map", {})

    result.unmodified = unmodified_count

    # ── Dry run: just print what would happen ──────────────────
    if dry_run:
        result.added = len(added)
        result.modified = len(modified)
        result.deleted = len(deleted)
        result.dirs_created = len(mkdir)
        result.dirs_removed = len(rmdir)

        if added:
            click.echo(click.style("+ Added:", fg="green"))
            for f in added:
                _echo_file_entry(f, "+", "green")

        if modified:
            click.echo(click.style("~ Modified:", fg="yellow"))
            for f in modified:
                _echo_file_entry(f, "~", "yellow")

        if deleted:
            click.echo(click.style("- Deleted:", fg="red"))
            for f in deleted:
                _echo_file_entry(f, "-", "red")

        if mkdir:
            click.echo(click.style("📁 Dirs to create:", fg="cyan"))
            for d in mkdir:
                click.echo(f"  + {d}")

        if rmdir:
            click.echo(click.style("📁 Dirs to remove:", fg="cyan"))
            for d in rmdir:
                click.echo(f"  - {d}")

        return result

    # Nothing to do?
    if not added and not modified and not deleted and not mkdir and not rmdir:
        return result

    # ── 3. Cleanup stale files ─────────────────────────────────
    stale_file_ids = [
        *[d["file_id"] for d in deleted],
        *[m["stale_file_id"] for m in modified],
    ]

    if stale_file_ids or rmdir:
        if verbose:
            click.echo(
                f"Cleaning up {len(stale_file_ids)} files, {len(rmdir)} dirs...",
                err=True,
            )
        client.sync_cleanup(kb_id, stale_file_ids, rmdir if rmdir else None)
        result.deleted = len(deleted)
        result.dirs_removed = len(rmdir)

    # ── 4. Create missing directories ──────────────────────────
    for dir_path in mkdir:
        segments = dir_path.split("/")
        name = segments[-1]
        parent_path = "/".join(segments[:-1])
        parent_id = directory_map.get(parent_path)

        if verbose:
            click.echo(f"  mkdir {dir_path}", err=True)

        resp = client.create_directory(kb_id, name, parent_id)
        directory_map[dir_path] = resp.get("id", "")
        result.dirs_created += 1

    # ── 5. Upload files ────────────────────────────────────────
    # Build a lookup from manifest entries for fast access.
    manifest_by_key = {(e.path, e.filename): e for e in manifest}

    files_to_upload = [
        *[(a, "added") for a in added],
        *[(m, "modified") for m in modified],
    ]

    for i, (entry, change_type) in enumerate(files_to_upload, 1):
        filename = entry["filename"]
        path = entry.get("path", "")
        display = f"{path}/{filename}" if path else filename

        if verbose:
            click.echo(f"  [{i}/{len(files_to_upload)}] {display}", err=True)

        manifest_entry = manifest_by_key.get((path, filename))
        if not manifest_entry:
            result.errors.append(f"File not in manifest: {display}")
            continue

        try:
            content = connector.read_file(path, filename)
            directory_id = directory_map.get(path) if path else None

            client.upload_file(
                file_content=content,
                filename=filename,
                kb_id=kb_id,
                file_hash=manifest_entry.checksum,
                directory_id=directory_id,
            )

            if change_type == "added":
                result.added += 1
            else:
                result.modified += 1

        except Exception as e:
            result.errors.append(f"{display}: {e}")
            click.echo(
                click.style(f"  ✗ {display}: {e}", fg="red"),
                err=True,
            )

    return result


def _echo_file_entry(entry: dict, prefix: str, color: str) -> None:
    """Print a file entry with color."""
    path = entry.get("path", "")
    filename = entry["filename"]
    display = f"{path}/{filename}" if path else filename
    click.echo(click.style(f"  {prefix} {display}", fg=color))
