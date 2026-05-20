# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.2.0] - 2025-05-20

### Added

- `oikb daemon` command: long-lived scheduler with FastAPI server, /health and /history endpoints.
- `oikb history` command: view sync history from local SQLite database.
- Webhook support: /webhooks/github, /webhooks/gitlab, /webhooks/slack, /webhooks/confluence for real-time sync triggers.
- `--json` output flag for `history` command.
- 13 new connectors: Document360, Slab, Outline, Google Sites, Egnyte, Oracle Cloud Storage, ProductBoard, XenForo, Zulip, Gong, Fireflies, DokuWiki, ServiceNow. Total: 44 connectors.
- Multi-KB routing: `routes` key in `.oikb.yaml` to route files by glob pattern to different KBs.
- Selective sync filters: `filter.include` / `filter.exclude` glob patterns to narrow sync scope.
- Daemon doubles as an OpenAPI tool server for Open WebUI (Settings → Connections → Tool Server).

### Changed

- FastAPI and uvicorn are now core dependencies.

## [0.1.3] - 2025-05-20

### Changed

- Renamed `.oikb.yaml` config key from `kb` to `kb-id` to align with the CLI flag.

## [0.1.2] - 2025-05-20

### Changed

- Messaging connectors (Slack, Discord, Teams) now split messages by day for truly incremental sync. Past days are immutable so their checksums never change.

## [0.1.1] - 2025-05-20

### Added

- **28 new connectors** bringing the total to 31, covering code repos, cloud storage, wikis, ticketing, messaging, CRM, and web:
  - **Code Repos**: GitLab (`gitlab:owner/repo`), Bitbucket (`bitbucket:owner/repo`)
  - **Cloud Storage**: Google Cloud Storage (`gs://`), Azure Blob (`az://`), Dropbox (`dropbox:`), Cloudflare R2 (`r2://`)
  - **Wikis & Knowledge Bases**: Confluence (`confluence:`), Notion (`notion:`), BookStack (`bookstack:`), Discourse (`discourse:`), GitBook (`gitbook:`), Guru (`guru:`)
  - **Ticketing & Tasks**: Jira (`jira:`), Linear (`linear:`), Zendesk (`zendesk:`), Freshdesk (`freshdesk:`), Asana (`asana:`), ClickUp (`clickup:`), Airtable (`airtable:`)
  - **Messaging**: Slack (`slack:`), Discord (`discord:`), Microsoft Teams (`teams:`), Gmail (`gmail:`)
  - **Sales & CRM**: Salesforce (`salesforce:`), HubSpot (`hubspot:`)
  - **Other**: Google Drive (`gdrive:`), SharePoint (`sharepoint:`), Web Crawler (`web:`)
- Context manager support for `OikbClient`
- `.gitignore` added to the project

### Changed

- Renamed `--kb` to `--kb-id` across all commands
- Modernized README with 30+ connector showcase organized by category
- Added Open WebUI 0.9.6+ version requirement note
- Updated author to Tim Baek
- Moved `import json` to top-level in `client.py`
- Removed unused imports from `sync.py`, `config.py`
- Fixed `Optional[str]` type hints to use `str | None` syntax
- Removed redundant `fnmatch` check in `ignore.py`
- Empty source message now respects `--quiet` flag

## [0.1.0] - 2025-05-20

### Added

- Initial release of oikb, a CLI tool for syncing content to Open WebUI Knowledge Bases.
- Incremental sync (`oikb sync`) with SHA-256 diffing. Supports local directories, GitHub repos, and S3 buckets.
- Dry-run preview (`oikb diff`).
- Watch mode (`oikb watch`) with debounced filesystem monitoring via watchdog.
- List files (`oikb ls`), status (`oikb status`), reset (`oikb reset`) commands.
- Configuration (`oikb config`) via config file, env vars, or CLI flags.
- Declarative config (`.oikb.yaml`) for multi-source sync.
- Ignore patterns (`.oikbignore`) with gitignore-style file exclusion.
- GitHub connector (`github:owner/repo`) via Trees API. No local clone needed.
- S3 connector (`s3://bucket/prefix`) via boto3 using ETags as checksums.
- Docker image with multi-arch support (amd64 + arm64).
- GitHub Actions workflows for Docker builds (GHCR) and releases.
