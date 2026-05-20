# 📚 oikb

A CLI tool that syncs content to [Open WebUI](https://github.com/open-webui/open-webui) Knowledge Bases. 30+ connectors for local files, Git repos, cloud storage, wikis, ticketing, messaging, CRM, and more.

> [!IMPORTANT]
> Requires **Open WebUI 0.9.6+** (uses the Knowledge Base sync API).

## Why oikb?

Manually uploading files to Knowledge Bases is tedious. oikb automates it with incremental SHA-256 diffing, so only new and modified files are uploaded. Directory structure is mirrored automatically. Run it once, run it in CI, or leave it watching for changes.

## Connectors

oikb connects to all your tools. One CLI, incremental sync, automatic directory mirroring.

### Code Repositories

| Source | Syntax | Auth |
|---|---|---|
| **GitHub** | `github:owner/repo` | `GITHUB_TOKEN` |
| **GitLab** | `gitlab:owner/repo` | `GITLAB_TOKEN` |
| **Bitbucket** | `bitbucket:owner/repo` | `BITBUCKET_USER` + `BITBUCKET_APP_PASSWORD` |

### Cloud Storage

| Source | Syntax | Auth |
|---|---|---|
| **Local directory** | `./docs` | - |
| **Amazon S3** | `s3://bucket/prefix` | AWS credentials |
| **Google Cloud Storage** | `gs://bucket/prefix` | `GOOGLE_APPLICATION_CREDENTIALS` |
| **Azure Blob Storage** | `az://container/prefix` | `AZURE_STORAGE_CONNECTION_STRING` |
| **Dropbox** | `dropbox:/path` | `DROPBOX_TOKEN` |
| **Cloudflare R2** | `r2://bucket/prefix` | `R2_ACCOUNT_ID` + R2 keys |

### Knowledge Bases & Wikis

| Source | Syntax | Auth |
|---|---|---|
| **Confluence** | `confluence:SPACEKEY` | `CONFLUENCE_URL` + `CONFLUENCE_TOKEN` |
| **Notion** | `notion:<database-id>` | `NOTION_TOKEN` |
| **BookStack** | `bookstack:` | `BOOKSTACK_URL` + `BOOKSTACK_TOKEN_*` |
| **Discourse** | `discourse:category` | `DISCOURSE_URL` + `DISCOURSE_API_KEY` |
| **GitBook** | `gitbook:<space-id>` | `GITBOOK_TOKEN` |
| **Guru** | `guru:` | `GURU_USER` + `GURU_TOKEN` |

### Ticketing & Task Management

| Source | Syntax | Auth |
|---|---|---|
| **Jira** | `jira:PROJECT` | `JIRA_URL` + `JIRA_TOKEN` |
| **Linear** | `linear:<team-id>` | `LINEAR_TOKEN` |
| **Asana** | `asana:<project-id>` | `ASANA_TOKEN` |
| **ClickUp** | `clickup:<space-id>` | `CLICKUP_TOKEN` |
| **Zendesk** | `zendesk:<subdomain>` | `ZENDESK_SUBDOMAIN` + `ZENDESK_TOKEN` |
| **Freshdesk** | `freshdesk:<domain>` | `FRESHDESK_DOMAIN` + `FRESHDESK_TOKEN` |
| **Airtable** | `airtable:<base-id>` | `AIRTABLE_TOKEN` |

### Messaging

| Source | Syntax | Auth |
|---|---|---|
| **Slack** | `slack:<channel-id>` | `SLACK_TOKEN` |
| **Discord** | `discord:<channel-id>` | `DISCORD_TOKEN` |
| **Microsoft Teams** | `teams:<team-id>/<channel-id>` | `TEAMS_*` credentials |
| **Gmail** | `gmail:user@domain.com` | `GOOGLE_APPLICATION_CREDENTIALS` |

### Sales & CRM

| Source | Syntax | Auth |
|---|---|---|
| **Salesforce** | `salesforce:` | `SALESFORCE_URL` + `SALESFORCE_TOKEN` |
| **HubSpot** | `hubspot:` | `HUBSPOT_TOKEN` |

### Other

| Source | Syntax | Auth |
|---|---|---|
| **Website / Sitemap** | `web:https://docs.example.com` | - |
| **Google Drive** | `gdrive:<folder-id>` | `GOOGLE_APPLICATION_CREDENTIALS` |
| **SharePoint** | `sharepoint:site/library` | `SHAREPOINT_*` credentials |

Most connectors use `httpx` (included). Some require an extra:

```bash
pip install oikb[gdrive]    # Google Drive
pip install oikb[gmail]     # Gmail
pip install oikb[s3]        # Amazon S3, Cloudflare R2
pip install oikb[gcs]       # Google Cloud Storage
pip install oikb[azure]     # Azure Blob Storage
pip install oikb[dropbox]   # Dropbox
pip install oikb[web]       # Web crawler
pip install oikb[all]       # Everything
```

## Getting Started

### Docker (recommended)

```bash
docker run --rm \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb sync /data --kb-id your-kb-id
```

### pip

```bash
pip install oikb
```

```bash
export OPEN_WEBUI_URL=http://localhost:3000
export OPEN_WEBUI_API_KEY=sk-your-api-key

oikb sync ./docs --kb-id your-kb-id
```

> [!TIP]
> No config file needed. Env vars are enough. You can also use `oikb config set url ...` and `oikb config set token ...` to save them to `~/.config/oikb/config.yaml`.

## Commands

```bash
# Sync from any connector
oikb sync ./docs --kb-id your-kb-id
oikb sync github:owner/repo --kb-id your-kb-id
oikb sync confluence:ENG --kb-id your-kb-id
oikb sync notion:abc123 --kb-id your-kb-id
oikb sync slack:C0123ABC --kb-id your-kb-id
oikb sync jira:PROJ --kb-id your-kb-id
oikb sync s3://bucket/prefix --kb-id your-kb-id
oikb sync web:https://docs.example.com --kb-id your-kb-id

# Preview changes without uploading
oikb diff ./docs --kb-id your-kb-id

# Watch for changes and auto-sync
oikb watch ./docs --kb-id your-kb-id

# List files / show info / reset
oikb ls --kb-id your-kb-id
oikb status --kb-id your-kb-id
oikb reset --kb-id your-kb-id
```

## Configuration

Settings are resolved in this order (highest priority wins):

1. **CLI flags** (`--url`, `--token`)
2. **Environment variables** (`OPEN_WEBUI_URL`, `OPEN_WEBUI_API_KEY`)
3. **Config file** (`~/.config/oikb/config.yaml`)

## Declarative Config (`.oikb.yaml`)

For recurring multi-source syncs:

```yaml
sync:
  - source: ./docs
    kb: project-docs

  - source: github:owner/wiki
    kb: team-wiki
    branch: main

  - source: confluence:ENG
    kb: eng-handbook

  - source: slack:C0123ABC
    kb: team-updates

  - source: jira:PROJ
    kb: project-issues
```

```bash
oikb sync              # Sync all entries
oikb sync --name docs  # Sync a specific entry
```

## Docker

Published at `ghcr.io/open-webui/oikb`.

```bash
# One-shot sync
docker run --rm \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb sync /data --kb-id your-kb-id

# Watch mode
docker run --rm -d \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb watch /data --kb-id your-kb-id
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
    volumes:
      - ./docs:/data
    command: watch /data --kb-id ${KB_ID}
    depends_on:
      - open-webui
    restart: unless-stopped
```

### GitHub Actions

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

1. Scan source (local dir, GitHub, Confluence, S3, etc.), compute checksums
2. Send manifest to Open WebUI's `/sync/diff` endpoint
3. Server diffs against stored file hashes
4. Delete stale files, create missing directories
5. Upload only new and modified files

## License

MIT. See [LICENSE](LICENSE) for details.
