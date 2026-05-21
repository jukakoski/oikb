"""oikb daemon -- FastAPI server with built-in scheduler."""

from __future__ import annotations

import asyncio
import hmac
import logging
import os
import signal
import time
from pathlib import Path
from typing import Any, Optional

import click
import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from oikb.env import API_KEY
from oikb.history import SyncHistory

log = logging.getLogger(__name__)

# ── Auth dependency ──────────────────────────────────────────────

bearer_scheme = HTTPBearer(auto_error=False)


async def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    if not API_KEY:
        return
    if not credentials or not hmac.compare_digest(credentials.credentials, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


app = FastAPI(
    title="oikb",
    description="Sync engine for Open WebUI Knowledge Bases. Trigger syncs, check status, and query history.",
    version="0.2.3",
)

# Runtime state populated by start_daemon().
_scheduler_state: dict[str, dict[str, Any]] = {}
_history: SyncHistory | None = None
_entries: list[dict] = []
_shutdown_event: asyncio.Event | None = None


# ── Interval parser ──────────────────────────────────────────────

def parse_interval(value: str | int) -> int:
    """Parse an interval string like '5m', '1h', '30s' to seconds."""
    if isinstance(value, (int, float)):
        return int(value)
    value = value.strip().lower()
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    if value[-1] in multipliers:
        return int(value[:-1]) * multipliers[value[-1]]
    return int(value)


# ── FastAPI routes ───────────────────────────────────────────────

@app.get(
    "/health",
    operation_id="get_sync_status",
    summary="Get sync status for all configured sources",
)
async def health():
    """Returns the current sync status for every configured source, including last sync time, duration, file counts, and any errors. Use this to check if syncs are running and healthy."""
    return {
        "status": "ok",
        "sources": _scheduler_state,
    }


@app.get("/health/ready", include_in_schema=False)
async def ready():
    """Liveness probe."""
    return {"ready": True}


@app.get(
    "/history",
    operation_id="get_sync_history",
    summary="Query sync history log",
    dependencies=[Depends(verify_api_key)],
)
async def history_endpoint(
    limit: int = 50,
    kb_id: str | None = None,
    errors_only: bool = False,
):
    """Returns recent sync history entries from the local database. Filter by Knowledge Base ID or show only errors. Each entry includes source, status, duration, and file change counts."""
    if not _history:
        return {"entries": []}
    entries = await asyncio.to_thread(
        _history.query, limit=limit, kb_id=kb_id, errors_only=errors_only,
    )
    return {"entries": entries}


@app.post(
    "/sync/{identifier}",
    operation_id="trigger_sync",
    summary="Trigger an immediate sync by alias or KB ID",
    dependencies=[Depends(verify_api_key)],
)
async def trigger_sync(identifier: str):
    """Triggers an immediate sync matching the given alias or Knowledge Base ID. The sync runs asynchronously in the background. Use get_sync_status to check progress."""
    for entry in _entries:
        if entry.get("name") == identifier or entry.get("kb-id") == identifier:
            asyncio.create_task(_run_entry(entry))
            return {"triggered": True, "name": entry.get("name"), "kb_id": entry.get("kb-id")}
    return {"triggered": False, "error": f"No entry matching '{identifier}'"}


# ── Scheduler ────────────────────────────────────────────────────

async def _run_entry(entry: dict) -> None:
    """Run a single sync for an entry."""
    from oikb.cli import _make_client, _resolve_connector
    from oikb.sync import run_sync

    source = entry["source"]
    kb_id = entry["kb-id"]
    started_at = time.time()

    _scheduler_state[source] = {
        **_scheduler_state.get(source, {}),
        "status": "running",
        "started_at": started_at,
    }

    try:
        connector = _resolve_connector(
            source,
            branch=entry.get("branch"),
            path=entry.get("path"),
        )
        client = _make_client(
            url=entry.get("url"),
            token=entry.get("token"),
        )
        result = run_sync(
            client=client,
            connector=connector,
            kb_id=kb_id,
            quiet=True,
        )
        client.close()

        duration_ms = int((time.time() - started_at) * 1000)

        _scheduler_state[source] = {
            "status": "success" if not result.errors else "partial",
            "last_sync": time.time(),
            "duration_ms": duration_ms,
            "files_added": result.added,
            "files_modified": result.modified,
            "files_deleted": result.deleted,
            "unmodified": result.unmodified,
            "errors": result.errors or [],
        }

        if _history:
            await asyncio.to_thread(
                _history.log,
                source=source,
                kb_id=kb_id,
                status="success",
                started_at=started_at,
                files_added=result.added,
                files_modified=result.modified,
                files_deleted=result.deleted,
                unmodified=result.unmodified,
            )

        log.info(
            f"Synced {source} -> {kb_id}: {result.summary()} ({duration_ms}ms)"
        )

    except Exception as e:
        _scheduler_state[source] = {
            "status": "error",
            "last_sync": time.time(),
            "error": str(e),
        }
        if _history:
            await asyncio.to_thread(
                _history.log,
                source=source,
                kb_id=kb_id,
                status="error",
                started_at=started_at,
                error=str(e),
            )
        log.error(f"Sync failed for {source}: {e}")


async def _schedule_entry(entry: dict) -> None:
    """Run sync for one .oikb.yaml entry on a loop."""
    interval = parse_interval(entry.get("interval", "30m"))
    source = entry.get("source", "unknown")

    log.info(f"Scheduling {source} every {interval}s")

    while not _shutdown_event.is_set():
        await _run_entry(entry)

        # Calculate next sync time.
        _scheduler_state.setdefault(source, {})["next_sync_in"] = f"{interval}s"

        try:
            await asyncio.wait_for(_shutdown_event.wait(), timeout=interval)
            break  # Shutdown requested.
        except asyncio.TimeoutError:
            pass  # Interval elapsed, run again.


async def _run_scheduler(entries: list[dict]) -> None:
    """Start all sync tasks and wait for shutdown."""
    global _shutdown_event
    _shutdown_event = asyncio.Event()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown_event.set)

    tasks = [asyncio.create_task(_schedule_entry(e)) for e in entries]

    await _shutdown_event.wait()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


# ── Entry point ──────────────────────────────────────────────────

def start_daemon(
    entries: list[dict],
    port: int = 8080,
    no_server: bool = False,
) -> None:
    """Start the daemon with scheduler + optional HTTP server."""
    global _history, _entries
    _entries = entries
    _history = SyncHistory()

    # Mount webhook routes.
    from oikb.webhooks import router as webhook_router, configure as configure_webhooks
    app.include_router(webhook_router)

    secrets: dict[str, str] = {}
    for entry in entries:
        for key in ("github_secret", "gitlab_secret", "slack_signing_secret"):
            if key in entry:
                secrets[key] = str(entry[key])
    configure_webhooks(entries=entries, run_entry=_run_entry, secrets=secrets)

    webhook_entries = [e for e in entries if e.get("webhook")]

    if no_server:
        asyncio.run(_run_scheduler(entries))
    else:
        @app.on_event("startup")
        async def _startup():
            asyncio.create_task(_run_scheduler(entries))

        click.echo(f"oikb daemon listening on port {port}")
        click.echo(f"  {len(entries)} source(s) configured")
        click.echo(f"  Auth: {'OIKB_API_KEY set' if API_KEY else 'disabled (set OIKB_API_KEY to enable)'}")
        if webhook_entries:
            click.echo(f"  {len(webhook_entries)} webhook-enabled source(s)")
        click.echo(f"  GET  http://localhost:{port}/health")
        click.echo(f"  GET  http://localhost:{port}/history")
        click.echo(f"  POST http://localhost:{port}/sync/{{kb_id}}")
        if webhook_entries:
            click.echo(f"  POST http://localhost:{port}/webhooks/github|gitlab|slack|confluence")
        click.echo(f"\n  OpenAPI spec: http://localhost:{port}/openapi.json")
        click.echo(f"  Add as Tool Server in Open WebUI → Settings → Connections")

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=port,
            log_level="warning",
        )
