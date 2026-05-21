"""Prometheus metrics for the oikb daemon."""

from __future__ import annotations

from prometheus_client import Counter, Histogram, Info

# ── Counters ─────────────────────────────────────────────────────

SYNC_TOTAL = Counter(
    "oikb_sync_total",
    "Total sync operations",
    ["source", "status"],
)

FILES_UPLOADED = Counter(
    "oikb_files_uploaded_total",
    "Total files uploaded (added + modified)",
    ["source"],
)

FILES_DELETED = Counter(
    "oikb_files_deleted_total",
    "Total files deleted during sync",
    ["source"],
)

SYNC_ERRORS = Counter(
    "oikb_sync_errors_total",
    "Total failed sync operations",
    ["source"],
)

# ── Histograms ───────────────────────────────────────────────────

SYNC_DURATION = Histogram(
    "oikb_sync_duration_seconds",
    "Sync duration in seconds",
    ["source"],
    buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800),
)

# ── Info ─────────────────────────────────────────────────────────

BUILD_INFO = Info(
    "oikb",
    "oikb build information",
)


def set_build_info(version: str) -> None:
    """Set build info labels (called once on startup)."""
    BUILD_INFO.info({"version": version})


def record_sync(
    source: str,
    status: str,
    duration_seconds: float,
    files_added: int = 0,
    files_modified: int = 0,
    files_deleted: int = 0,
) -> None:
    """Record metrics for a completed sync operation."""
    SYNC_TOTAL.labels(source=source, status=status).inc()
    SYNC_DURATION.labels(source=source).observe(duration_seconds)

    uploaded = files_added + files_modified
    if uploaded:
        FILES_UPLOADED.labels(source=source).inc(uploaded)
    if files_deleted:
        FILES_DELETED.labels(source=source).inc(files_deleted)
    if status == "error":
        SYNC_ERRORS.labels(source=source).inc()
