"""ServiceNow connector -- sync tickets/articles from a ServiceNow instance."""

from __future__ import annotations

import hashlib
import json as json_mod
import os

import httpx

from oikb.connectors import BaseConnector, ManifestEntry


class ServiceNowConnector(BaseConnector):
    """Sync records from ServiceNow Table API.

    Configurable:
      - table: which table to query (incident, kb_knowledge, change_request, etc.)
      - fields: which fields to export per record
      - query: ServiceNow encoded query string for filtering
      - format: output format — 'markdown' (default) or 'json'
      - limit: max records to fetch (default 1000)
    """

    def __init__(
        self,
        table: str = "incident",
        fields: list[str] | None = None,
        query: str | None = None,
        fmt: str = "markdown",
        limit: int = 1000,
        instance: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self._instance = instance or os.environ.get("SERVICENOW_INSTANCE", "")
        self._user = user or os.environ.get("SERVICENOW_USER", "")
        self._password = password or os.environ.get("SERVICENOW_PASSWORD", "")
        if not self._instance or not self._user or not self._password:
            raise ValueError("Set SERVICENOW_INSTANCE, SERVICENOW_USER, SERVICENOW_PASSWORD env vars.")
        self._table = table
        self._fields = fields or ["number", "short_description", "description", "state", "priority", "assigned_to"]
        self._query = query or ""
        self._fmt = fmt
        self._limit = limit
        self._http = httpx.Client(
            base_url=f"https://{self._instance}.service-now.com",
            auth=(self._user, self._password),
            headers={"Accept": "application/json"},
            timeout=30.0,
        )
        self._cache: dict[str, str] = {}

    def _resolve_value(self, val) -> str:
        """Extract display value from ServiceNow field."""
        if isinstance(val, dict):
            return val.get("display_value", val.get("value", str(val)))
        return str(val) if val else ""

    def _format_record(self, record: dict) -> tuple[str, str]:
        """Format a record and return (filename, content)."""
        number = record.get("number", record.get("sys_id", "unknown"))

        if self._fmt == "json":
            data = {f: self._resolve_value(record.get(f, "")) for f in self._fields}
            data["_table"] = self._table
            text = json_mod.dumps(data, indent=2, ensure_ascii=False)
            return f"{number}.json", text

        # Default: markdown
        short_desc = record.get("short_description", "")
        lines = [f"# {number}: {self._resolve_value(short_desc)}", ""]
        for field in self._fields:
            val = self._resolve_value(record.get(field, ""))
            if val:
                lines.append(f"**{field}**: {val}")
        return f"{number}.md", "\n".join(lines)

    def build_manifest(self) -> list[ManifestEntry]:
        params: dict = {
            "sysparm_fields": ",".join(self._fields),
            "sysparm_limit": str(self._limit),
        }
        if self._query:
            params["sysparm_query"] = self._query

        resp = self._http.get(f"/api/now/table/{self._table}", params=params)
        resp.raise_for_status()
        records = resp.json().get("result", [])

        entries: list[ManifestEntry] = []
        for record in records:
            filename, text = self._format_record(record)
            checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
            entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
            self._cache[filename] = text
        return entries

    def read_file(self, path: str, filename: str) -> bytes:
        return (self._cache.get(filename) or "").encode("utf-8")

    def close(self) -> None:
        self._http.close()


def parse_servicenow_source(source: str) -> dict[str, str]:
    """Parse servicenow:<table> or servicenow:<table>?query=...&fields=...&format=...&limit=..."""
    raw = source.removeprefix("servicenow:")
    parts = raw.split("?", 1)
    table = parts[0] or "incident"
    result: dict[str, str] = {"table": table}
    if len(parts) > 1:
        for param in parts[1].split("&"):
            if "=" in param:
                k, v = param.split("=", 1)
                result[k] = v
    return result
