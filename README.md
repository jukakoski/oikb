# 📚 oikb

Keep your [Open WebUI](https://github.com/open-webui/open-webui) Knowledge Bases in sync. Point it at a local directory, a GitHub repo, a Confluence space, an S3 bucket, or any of 44 supported sources. Only new and modified files are uploaded via incremental SHA-256 diffing.

> [!IMPORTANT]
> Requires **Open WebUI 0.9.6+**

## Quick Start

```bash
pip install oikb

export OPEN_WEBUI_URL=http://localhost:3000
export OPEN_WEBUI_API_KEY=sk-your-api-key

# Sync a directory to a Knowledge Base
oikb sync ./docs --kb-id your-kb-id

# Or watch for changes and auto-sync continuously
oikb watch ./docs --kb-id your-kb-id
```

## Commands

| Command | Description |
|---|---|
| `oikb sync <source>` | Incremental sync to a Knowledge Base |
| `oikb watch <dir>` | Watch for changes and auto-sync |
| `oikb daemon` | Long-lived scheduler with HTTP API |
| `oikb diff <source>` | Preview what a sync would do |
| `oikb history` | View sync history |
| `oikb ls` | List files in a Knowledge Base |
| `oikb status` | Show KB info and file count |
| `oikb reset` | Delete all files in a Knowledge Base |
| `oikb config` | Manage saved URL and API key |

## Daemon

Run `oikb daemon` for production deployments. Reads `.oikb.yaml` and syncs each source on a schedule.

```bash
oikb daemon --port 8080
```

Features:
- **Scheduled sync** — configurable per-source intervals (`30m`, `1h`, `6h`)
- **Webhooks** — instant sync on push via `/webhooks/github`, `/webhooks/gitlab`, `/webhooks/slack`, `/webhooks/confluence`
- **Health checks** — `GET /health` for Docker/K8s readiness probes
- **Sync history** — `GET /history` queryable log of all syncs
- **On-demand sync** — `POST /sync/{identifier}` trigger by `name` or `kb-id`
- **API key auth** — set `OIKB_API_KEY` to secure endpoints (Docker secrets `_FILE` supported)
- **OpenAPI tool server** — add `http://oikb:8080` as a Tool Server in Open WebUI (Settings → Connections) and let the LLM trigger syncs, check status, and query history

```yaml
# .oikb.yaml
sources:
  - name: wiki
    source: github:owner/repo
    kb-id: 8f3a2b1c-...
    interval: 1h
    webhook: true

  - name: handbook
    source: confluence:ENG
    kb-id: 4e7d9a0f-...
    interval: 6h
```

```bash
oikb sync --name wiki          # CLI: sync a specific entry
curl -X POST /sync/wiki        # API: trigger by name
curl -X POST /sync/8f3a2b1c-.. # API: trigger by kb-id
```

### Docker Compose

```yaml
services:
  open-webui:
    image: ghcr.io/open-webui/open-webui:main
    ports:
      - "3000:8080"

  oikb:
    image: ghcr.io/open-webui/oikb:latest
    environment:
      - OPEN_WEBUI_URL=http://open-webui:8080
      - OPEN_WEBUI_API_KEY=${OPEN_WEBUI_API_KEY}
      - OIKB_API_KEY=${OIKB_API_KEY}
    volumes:
      - ./.oikb.yaml:/app/.oikb.yaml:ro
    command: daemon
    ports:
      - "8080:8080"
    depends_on:
      - open-webui
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health/ready"]
      interval: 30s
      timeout: 5s
```

## 44 Connectors

| Category | Sources |
|---|---|
| **Code Repos** | GitHub, GitLab, Bitbucket |
| **Cloud Storage** | S3, GCS, Azure Blob, Dropbox, R2, Google Drive, SharePoint, Egnyte, Oracle Cloud |
| **Wikis & KBs** | Confluence, Notion, BookStack, Discourse, GitBook, Guru, Outline, Slab, Document360, DokuWiki, Google Sites |
| **Ticketing** | Jira, Linear, Zendesk, Freshdesk, Asana, ClickUp, Airtable, ServiceNow, ProductBoard |
| **Messaging** | Slack, Discord, Microsoft Teams, Gmail, Zulip |
| **Meetings** | Gong, Fireflies |
| **Forums** | XenForo |
| **Sales & CRM** | Salesforce, HubSpot |
| **Web** | Website / Sitemap crawler |

```bash
oikb sync github:owner/repo --kb-id your-kb-id
oikb sync confluence:ENG --kb-id your-kb-id
oikb sync s3://bucket/prefix --kb-id your-kb-id
oikb sync servicenow:incident --kb-id your-kb-id
```

Some connectors need an optional extra: `pip install oikb[gdrive]`, `pip install oikb[s3]`, or `pip install oikb[all]` for everything.

## Multi-KB Routing

Route files from a single source to different Knowledge Bases by glob pattern:

```yaml
sources:
  - name: wiki
    source: github:owner/repo
    kb-id: 8f3a2b1c-...
    routes:
      "docs/**/*.md": docs-kb-id
      "src/**": code-kb-id
```

## Selective Sync Filters

Narrow what gets synced with include/exclude globs:

```yaml
sources:
  - name: docs
    source: github:owner/repo
    kb-id: 4e7d9a0f-...
    filter:
      include: ["docs/**/*.md", "*.txt"]
      exclude: ["drafts/**"]
```

## Configuration

Resolved in order (highest priority wins):

1. **CLI flags** (`--url`, `--token`)
2. **Environment variables** (`OPEN_WEBUI_URL`, `OPEN_WEBUI_API_KEY`)
3. **Config file** (`~/.config/oikb/config.yaml`)

## History

```bash
oikb history                    # Table view
oikb history --json             # JSON output
oikb history --errors           # Failed syncs only
oikb history --clear --days 7   # Prune old entries
```

## GitHub Actions

```yaml
- name: Sync docs to Open WebUI
  uses: docker://ghcr.io/open-webui/oikb:latest
  with:
    args: sync /github/workspace/docs --kb-id ${{ secrets.KB_ID }}
  env:
    OPEN_WEBUI_URL: ${{ secrets.OPEN_WEBUI_URL }}
    OPEN_WEBUI_API_KEY: ${{ secrets.OPEN_WEBUI_API_KEY }}
```

## How It Works

1. Scan source, compute checksums
2. Send manifest to Open WebUI `/sync/diff`
3. Delete stale files, create missing directories
4. Upload only new and modified files

## License

MIT. See [LICENSE](LICENSE) for details.
