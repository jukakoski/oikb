# 📚 oikb

Keep your [Open WebUI](https://github.com/open-webui/open-webui) Knowledge Bases in sync. Point it at a local directory, a GitHub repo, a Confluence space, an S3 bucket, or any of 30+ supported sources. Only new and modified files are uploaded via incremental SHA-256 diffing.

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

Or with Docker:

```bash
docker run --rm \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb watch /data --kb-id your-kb-id
```

## Commands

| Command | Description |
|---|---|
| `oikb sync <source>` | Incremental sync to a Knowledge Base |
| `oikb watch <source>` | Watch for changes and auto-sync |
| `oikb diff <source>` | Preview what a sync would do |
| `oikb ls` | List files in a Knowledge Base |
| `oikb status` | Show KB info and file count |
| `oikb reset` | Delete all files in a Knowledge Base |
| `oikb config` | Manage saved URL and API key |

## 30+ Connectors

Beyond local directories, oikb can sync from remote sources using the same `oikb sync <source>` interface.

| Category | Sources |
|---|---|
| **Code Repos** | GitHub, GitLab, Bitbucket |
| **Cloud Storage** | S3, GCS, Azure Blob, Dropbox, R2, Google Drive, SharePoint |
| **Wikis & KBs** | Confluence, Notion, BookStack, Discourse, GitBook, Guru |
| **Ticketing** | Jira, Linear, Zendesk, Freshdesk, Asana, ClickUp, Airtable |
| **Messaging** | Slack, Discord, Microsoft Teams, Gmail |
| **Sales & CRM** | Salesforce, HubSpot |
| **Web** | Website / Sitemap crawler |

```bash
oikb sync github:owner/repo --kb-id your-kb-id
oikb sync confluence:ENG --kb-id your-kb-id
oikb sync s3://bucket/prefix --kb-id your-kb-id
oikb sync slack:C0123ABC --kb-id your-kb-id
```

Some connectors need an optional extra: `pip install oikb[gdrive]`, `pip install oikb[s3]`, or `pip install oikb[all]` for everything.

## Configuration

Resolved in order (highest priority wins):

1. **CLI flags** (`--url`, `--token`)
2. **Environment variables** (`OPEN_WEBUI_URL`, `OPEN_WEBUI_API_KEY`)
3. **Config file** (`~/.config/oikb/config.yaml`)

### Multi-source (`.oikb.yaml`)

Define multiple sources in a single config file:

```yaml
sync:
  - source: ./docs
    kb: project-docs
  - source: github:owner/wiki
    kb: team-wiki
    branch: main
  - source: confluence:ENG
    kb: eng-handbook
```

```bash
oikb sync              # Sync all entries
oikb sync --name docs  # Sync a specific entry
```

## Docker Compose

Run as a sidecar alongside Open WebUI:

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
