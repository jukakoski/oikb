"""Webhook routes for the oikb daemon -- real-time sync on push."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging

from fastapi import APIRouter, Request, HTTPException

log = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", include_in_schema=False)

# Set by daemon.py on startup.
_entries: list[dict] = []
_run_entry = None  # async callable
_secrets: dict[str, str] = {}


def configure(entries: list[dict], run_entry, secrets: dict[str, str]) -> None:
    """Called by daemon on startup to wire webhook state."""
    global _entries, _run_entry, _secrets
    _entries = entries
    _run_entry = run_entry
    _secrets = secrets


def _find_entry_by_source(prefix: str, match: str) -> dict | None:
    """Find a .oikb.yaml entry matching a source and with webhook: true."""
    for entry in _entries:
        source = entry.get("source", "")
        if source.startswith(prefix) and match in source and entry.get("webhook"):
            return entry
    return None


def _verify_hmac_sha256(payload: bytes, signature: str, secret: str) -> bool:
    """Validate HMAC-SHA256 signature."""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/github")
async def github_webhook(request: Request):
    """Handle GitHub push events."""
    payload = await request.body()

    secret = _secrets.get("github_secret", "")
    if secret:
        sig = request.headers.get("X-Hub-Signature-256", "")
        if not _verify_hmac_sha256(payload, sig, secret):
            raise HTTPException(status_code=403, detail="Invalid signature")

    data = await request.json()
    repo = data.get("repository", {}).get("full_name", "")
    entry = _find_entry_by_source("github:", repo)
    if entry and _run_entry:
        log.info(f"Webhook trigger: github push to {repo}")
        asyncio.create_task(_run_entry(entry))
        return {"status": "accepted", "source": entry["source"]}
    return {"status": "ignored", "reason": f"No matching entry for github:{repo}"}


@router.post("/gitlab")
async def gitlab_webhook(request: Request):
    """Handle GitLab push events."""
    secret = _secrets.get("gitlab_secret", "")
    if secret:
        token = request.headers.get("X-Gitlab-Token", "")
        if not hmac.compare_digest(token, secret):
            raise HTTPException(status_code=403, detail="Invalid token")

    data = await request.json()
    project = data.get("project", {}).get("path_with_namespace", "")
    entry = _find_entry_by_source("gitlab:", project)
    if entry and _run_entry:
        log.info(f"Webhook trigger: gitlab push to {project}")
        asyncio.create_task(_run_entry(entry))
        return {"status": "accepted", "source": entry["source"]}
    return {"status": "ignored"}


@router.post("/slack")
async def slack_webhook(request: Request):
    """Handle Slack Events API."""
    data = await request.json()

    # URL verification challenge.
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Validate signing secret if configured.
    secret = _secrets.get("slack_signing_secret", "")
    if secret:
        body = await request.body()
        ts = request.headers.get("X-Slack-Request-Timestamp", "")
        sig = request.headers.get("X-Slack-Signature", "")
        base = f"v0:{ts}:{body.decode()}"
        expected = "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, sig):
            raise HTTPException(status_code=403, detail="Invalid signature")

    event = data.get("event", {})
    channel = event.get("channel", "")
    entry = _find_entry_by_source("slack:", channel)
    if entry and _run_entry:
        log.info(f"Webhook trigger: slack message in {channel}")
        asyncio.create_task(_run_entry(entry))
        return {"status": "accepted"}
    return {"status": "ignored"}


@router.post("/confluence")
async def confluence_webhook(request: Request):
    """Handle Confluence page update webhooks."""
    data = await request.json()
    space_key = data.get("page", {}).get("spaceKey", "") or data.get("space", {}).get("key", "")
    entry = _find_entry_by_source("confluence:", space_key)
    if entry and _run_entry:
        log.info(f"Webhook trigger: confluence update in {space_key}")
        asyncio.create_task(_run_entry(entry))
        return {"status": "accepted"}
    return {"status": "ignored"}
