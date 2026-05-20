"""oikb CLI — command-line interface for Open WebUI Knowledge Base sync."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from oikb import __version__
from oikb.config import get_config, resolve_token, resolve_url, set_config


@click.group()
@click.version_option(version=__version__, prog_name="oikb")
@click.option("-q", "--quiet", is_flag=True, default=False, help="Suppress non-error output.")
@click.pass_context
def cli(ctx: click.Context, quiet: bool):
    """oikb — sync content to Open WebUI Knowledge Bases."""
    ctx.ensure_object(dict)
    ctx.obj["quiet"] = quiet


# ── Common options ──────────────────────────────────────────────

def common_options(f):
    """Shared --url, --token, --kb options."""
    f = click.option("--url", default=None, envvar="OPEN_WEBUI_URL", help="Open WebUI base URL.")(f)
    f = click.option("--token", default=None, envvar="OPEN_WEBUI_API_KEY", help="API key.")(f)
    f = click.option("--kb", default=None, help="Knowledge Base ID.")(f)
    return f


def _make_client(url: str | None, token: str | None):
    """Create an OikbClient from resolved config."""
    from oikb.client import OikbClient

    return OikbClient(
        base_url=resolve_url(url),
        token=resolve_token(token),
    )


def _resolve_connector(source: str, branch: str | None = None, path: str | None = None):
    """Resolve a source string to the appropriate connector.

    Supports:
      - Local paths: ./docs, /absolute/path, relative/path
      - GitHub: github:owner/repo[/subdir]
      - S3: s3://bucket[/prefix]
    """
    if source.startswith("github:"):
        from oikb.connectors.github import GitHubConnector, parse_github_source

        parsed = parse_github_source(source)
        return GitHubConnector(
            owner=parsed["owner"],
            repo=parsed["repo"],
            branch=branch,
            path=path or parsed.get("path"),
        )

    if source.startswith("s3://"):
        from oikb.connectors.s3 import S3Connector, parse_s3_source

        parsed = parse_s3_source(source)
        return S3Connector(
            bucket=parsed["bucket"],
            prefix=path or parsed.get("prefix"),
        )

    # Default: local filesystem.
    from oikb.connectors.filesystem import FilesystemConnector

    return FilesystemConnector(source)


def _load_oikb_yaml() -> list[dict] | None:
    """Load .oikb.yaml from the current directory if it exists."""
    import yaml

    yaml_path = Path(".oikb.yaml")
    if not yaml_path.exists():
        return None

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    if not data or "sync" not in data:
        return None

    return data["sync"]


# ── sync ────────────────────────────────────────────────────────

@cli.command()
@click.argument("source", required=False)
@common_options
@click.option("--branch", default=None, help="Branch for GitHub sources.")
@click.option("--path", "source_path", default=None, help="Subdirectory within the source.")
@click.option("--dry-run", is_flag=True, help="Preview changes without uploading.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed progress.")
@click.option("--name", default=None, help="Target a specific entry in .oikb.yaml by name/kb.")
@click.pass_context
def sync(
    ctx: click.Context,
    source: str | None,
    url: str | None,
    token: str | None,
    kb: str | None,
    branch: str | None,
    source_path: str | None,
    dry_run: bool,
    verbose: bool,
    name: str | None,
):
    """Incremental sync from a source to a Knowledge Base.

    SOURCE can be a local directory, github:owner/repo, or s3://bucket/prefix.
    If omitted, reads .oikb.yaml from the current directory.
    """
    quiet = ctx.obj.get("quiet", False)
    from oikb.sync import run_sync

    # ── .oikb.yaml mode ──
    if source is None:
        entries = _load_oikb_yaml()
        if not entries:
            click.echo(
                click.style("No source specified and no .oikb.yaml found.", fg="red"),
                err=True,
            )
            sys.exit(1)

        # Filter by --name if specified.
        if name:
            entries = [e for e in entries if e.get("kb") == name or e.get("source") == name]
            if not entries:
                click.echo(click.style(f"No entry matching '{name}' in .oikb.yaml", fg="red"), err=True)
                sys.exit(1)

        has_errors = False
        for entry in entries:
            entry_source = entry.get("source")
            entry_kb = entry.get("kb")
            entry_branch = entry.get("branch")
            entry_path = entry.get("path")

            if not entry_source or not entry_kb:
                click.echo(click.style(f"Skipping invalid entry: {entry}", fg="yellow"), err=True)
                continue

            if not quiet:
                click.echo(f"\n{'─' * 40}")
                click.echo(f"Syncing: {entry_source} → {entry_kb}")

            try:
                connector = _resolve_connector(entry_source, entry_branch, entry_path)
                client = _make_client(url, token)
                result = run_sync(
                    client=client,
                    connector=connector,
                    kb_id=entry_kb,
                    dry_run=dry_run,
                    verbose=verbose,
                    quiet=quiet,
                )
                client.close()

                if not quiet:
                    prefix = "Dry run" if dry_run else "Done"
                    click.echo(f"  {prefix}: {result.summary()}")

                if result.errors:
                    has_errors = True

            except Exception as e:
                click.echo(click.style(f"  Failed: {e}", fg="red"), err=True)
                has_errors = True

        if has_errors:
            sys.exit(1)
        return

    # ── Single source mode ──
    if not kb:
        click.echo(click.style("--kb is required when syncing a single source.", fg="red"), err=True)
        sys.exit(1)

    try:
        connector = _resolve_connector(source, branch, source_path)
    except (FileNotFoundError, ImportError, ValueError) as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)

    try:
        client = _make_client(url, token)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        sys.exit(1)

    try:
        result = run_sync(
            client=client,
            connector=connector,
            kb_id=kb,
            dry_run=dry_run,
            verbose=verbose,
            quiet=quiet,
        )
    except Exception as e:
        click.echo(click.style(f"Sync failed: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        client.close()

    if not quiet:
        prefix = "Dry run" if dry_run else "Sync complete"
        click.echo(f"{prefix}: {result.summary()}")

    if result.errors:
        click.echo(click.style(f"\n{len(result.errors)} error(s):", fg="red"), err=True)
        for err in result.errors:
            click.echo(f"  • {err}", err=True)
        sys.exit(1)


# ── diff ────────────────────────────────────────────────────────

@cli.command()
@click.argument("source")
@common_options
@click.option("--branch", default=None, help="Branch for GitHub sources.")
@click.option("--path", "source_path", default=None, help="Subdirectory within the source.")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output.")
@click.pass_context
def diff(
    ctx: click.Context,
    source: str,
    url: str | None,
    token: str | None,
    kb: str | None,
    branch: str | None,
    source_path: str | None,
    verbose: bool,
):
    """Preview what a sync would do (alias for sync --dry-run)."""
    if not kb:
        click.echo(click.style("--kb is required.", fg="red"), err=True)
        sys.exit(1)

    from oikb.sync import run_sync

    try:
        connector = _resolve_connector(source, branch, source_path)
    except (FileNotFoundError, ImportError, ValueError) as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)

    try:
        client = _make_client(url, token)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        sys.exit(1)

    try:
        result = run_sync(
            client=client,
            connector=connector,
            kb_id=kb,
            dry_run=True,
            verbose=verbose,
        )
    except Exception as e:
        click.echo(click.style(f"Diff failed: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        client.close()

    click.echo(f"\n{result.summary()}")


# ── watch ───────────────────────────────────────────────────────

@cli.command()
@click.argument("directory")
@common_options
@click.option("--debounce", default=1.0, type=float, help="Seconds to wait after last change (default: 1.0).")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed progress.")
@click.pass_context
def watch(
    ctx: click.Context,
    directory: str,
    url: str | None,
    token: str | None,
    kb: str | None,
    debounce: float,
    verbose: bool,
):
    """Watch a local directory and sync on changes.

    Runs continuously until interrupted (Ctrl+C).
    """
    if not kb:
        click.echo(click.style("--kb is required.", fg="red"), err=True)
        sys.exit(1)

    quiet = ctx.obj.get("quiet", False)

    from oikb.watcher import watch_directory
    from oikb.connectors.filesystem import FilesystemConnector, DEFAULT_IGNORE
    from oikb.sync import run_sync

    try:
        client = _make_client(url, token)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        sys.exit(1)

    click.echo(f"Watching {directory} → KB {kb} (Ctrl+C to stop)")

    def on_change():
        try:
            connector = FilesystemConnector(directory)
            result = run_sync(
                client=client,
                connector=connector,
                kb_id=kb,
                verbose=verbose,
                quiet=quiet,
            )
            if not quiet:
                click.echo(f"  [{_timestamp()}] {result.summary()}")
        except Exception as e:
            click.echo(click.style(f"  [{_timestamp()}] Sync error: {e}", fg="red"), err=True)

    try:
        watch_directory(
            directory=directory,
            on_change=on_change,
            debounce_seconds=debounce,
            ignore=DEFAULT_IGNORE,
        )
    except FileNotFoundError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        client.close()


# ── reset ───────────────────────────────────────────────────────

@cli.command()
@common_options
@click.option(
    "--keep-directories",
    is_flag=True,
    help="Keep directory structure, only remove files.",
)
@click.confirmation_option(
    prompt="This will delete all files in the Knowledge Base. Continue?"
)
def reset(url: str | None, token: str | None, kb: str | None, keep_directories: bool):
    """Reset a Knowledge Base (delete all files)."""
    if not kb:
        click.echo(click.style("--kb is required.", fg="red"), err=True)
        sys.exit(1)

    try:
        client = _make_client(url, token)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        sys.exit(1)

    try:
        client.reset_kb(kb, include_directories=not keep_directories)
    except Exception as e:
        click.echo(click.style(f"Reset failed: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        client.close()

    click.echo("Knowledge Base reset.")


# ── ls ──────────────────────────────────────────────────────────

@cli.command()
@common_options
def ls(url: str | None, token: str | None, kb: str | None):
    """List files in a Knowledge Base."""
    if not kb:
        click.echo(click.style("--kb is required.", fg="red"), err=True)
        sys.exit(1)

    try:
        client = _make_client(url, token)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        sys.exit(1)

    try:
        files = client.list_kb_files(kb)
    except Exception as e:
        click.echo(click.style(f"Failed: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        client.close()

    if not files:
        click.echo("(empty)")
        return

    for f in files:
        meta = f.get("meta", {})
        name = meta.get("name", f.get("filename", "?"))
        size = meta.get("size", 0)
        file_hash = meta.get("file_hash", "")[:8]
        click.echo(f"  {name}  ({_format_size(size)})  {file_hash}")


# ── status ──────────────────────────────────────────────────────

@cli.command()
@common_options
def status(url: str | None, token: str | None, kb: str | None):
    """Show Knowledge Base info and file count."""
    if not kb:
        click.echo(click.style("--kb is required.", fg="red"), err=True)
        sys.exit(1)

    try:
        client = _make_client(url, token)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        sys.exit(1)

    try:
        info = client.get_kb(kb)
        files = info.get("files", [])
    except Exception as e:
        click.echo(click.style(f"Failed: {e}", fg="red"), err=True)
        sys.exit(1)
    finally:
        client.close()

    name = info.get("name", kb)
    description = info.get("description", "")
    file_count = len(files)
    total_size = sum(f.get("meta", {}).get("size", 0) for f in files)

    click.echo(f"Knowledge Base: {name}")
    if description:
        click.echo(f"  Description: {description}")
    click.echo(f"  ID:          {kb}")
    click.echo(f"  Files:       {file_count}")
    click.echo(f"  Total size:  {_format_size(total_size)}")

    updated_at = info.get("updated_at")
    if updated_at:
        click.echo(f"  Updated:     {updated_at}")


# ── config ──────────────────────────────────────────────────────

@cli.group()
def config():
    """Manage oikb configuration."""


@config.command("set")
@click.argument("key", type=click.Choice(["url", "token"]))
@click.argument("value")
def config_set(key: str, value: str):
    """Set a config value (url or token)."""
    set_config(key, value)
    display = value if key == "url" else f"{value[:4]}...{value[-4:]}"
    click.echo(f"{key} = {display}")


@config.command("get")
@click.argument("key", required=False)
def config_get(key: str | None):
    """Show config values."""
    data = get_config(key)
    if isinstance(data, dict):
        if not data:
            click.echo("(no config set)")
            return
        for k, v in data.items():
            display = v if k == "url" else f"{v[:4]}...{v[-4:]}" if v else ""
            click.echo(f"{k} = {display}")
    elif data:
        click.echo(data)
    else:
        click.echo("(not set)")


# ── Helpers ─────────────────────────────────────────────────────

def _format_size(size: int) -> str:
    """Human-readable file size."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _timestamp() -> str:
    """Current time as HH:MM:SS."""
    from datetime import datetime

    return datetime.now().strftime("%H:%M:%S")
