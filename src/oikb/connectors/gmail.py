"""Gmail connector — sync emails to a Knowledge Base.

Auth via service account with domain-wide delegation.
Requires: pip install oikb[gmail]
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

from oikb.connectors import BaseConnector, ManifestEntry


class GmailConnector(BaseConnector):
    """Sync emails from Gmail via the Gmail API."""

    def __init__(self, user_email: str, query: str = "", service_account_file: str | None = None, max_results: int = 500):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError("Gmail connector requires google-api-python-client. Install with: pip install oikb[gmail]")

        self.query = query or "newer_than:30d"
        self.max_results = max_results

        creds_file = service_account_file or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_file:
            raise ValueError("Google service account credentials required. Set GOOGLE_APPLICATION_CREDENTIALS env var.")

        creds = service_account.Credentials.from_service_account_file(
            creds_file, scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        ).with_subject(user_email)
        self._service = build("gmail", "v1", credentials=creds)
        self._cache: dict[str, str] = {}

    def build_manifest(self) -> list[ManifestEntry]:
        entries: list[ManifestEntry] = []
        page_token = None
        count = 0
        while count < self.max_results:
            resp = self._service.users().messages().list(
                userId="me", q=self.query, maxResults=min(100, self.max_results - count), pageToken=page_token,
            ).execute()
            for msg_meta in resp.get("messages", []):
                msg = self._service.users().messages().get(userId="me", id=msg_meta["id"], format="full").execute()
                headers = {h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])}
                subject = re.sub(r'[<>:"/\\|?*]', "_", headers.get("Subject", "No Subject"))
                date = headers.get("Date", "")
                body = self._extract_body(msg.get("payload", {}))
                text = f"From: {headers.get('From', '')}\nTo: {headers.get('To', '')}\nDate: {date}\nSubject: {subject}\n\n{body}"
                filename = f"{msg_meta['id']}_{subject[:50]}.txt"
                checksum = hashlib.sha256(text.encode()).hexdigest()[:16]
                entries.append(ManifestEntry(filename=filename, path="", checksum=checksum, size=len(text.encode())))
                self._cache[filename] = text
                count += 1
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        entries.sort(key=lambda e: e.display_path)
        return entries

    def _extract_body(self, payload: dict) -> str:
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        return ""

    def read_file(self, path: str, filename: str) -> bytes:
        text = self._cache.get(filename)
        if not text:
            raise FileNotFoundError(f"Email not found: {filename}")
        return text.encode("utf-8")


def parse_gmail_source(source: str) -> dict[str, str | None]:
    """Parse gmail:user@domain.com or gmail:user@domain.com?q=query."""
    source = source.removeprefix("gmail:")
    if "?" in source:
        email, qs = source.split("?", 1)
        query = qs.removeprefix("q=")
    else:
        email, query = source, ""
    if not email:
        raise ValueError("Invalid Gmail source. Expected: gmail:<user@domain.com>")
    return {"user_email": email, "query": query}
