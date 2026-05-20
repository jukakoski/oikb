# 📚 oikb

A CLI tool that syncs content to [Open WebUI](https://github.com/open-webui/open-webui) Knowledge Bases. Supports local directories, GitHub repos, and S3 buckets.

## Why oikb?

Manually uploading files to Knowledge Bases is tedious. oikb automates it with incremental SHA-256 diffing, so only new and modified files are uploaded. Directory structure is mirrored automatically. Run it once, run it in CI, or leave it watching for changes.

> [!IMPORTANT]
> Requires **Open WebUI 0.9.6+** (uses the `/sync/diff` and `/sync/cleanup` API endpoints).

## Getting Started

### Docker (recommended)

```bash
docker run --rm \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb sync /data --kb your-kb-id
```

### pip

```bash
pip install oikb
```

Then set your env vars and sync:

```bash
export OPEN_WEBUI_URL=http://localhost:3000
export OPEN_WEBUI_API_KEY=sk-your-api-key

oikb sync ./docs --kb your-kb-id
```

> [!TIP]
> No config file needed. Env vars are enough. You can also use `oikb config set url ...` and `oikb config set token ...` to save them to `~/.config/oikb/config.yaml`.

## Commands

```bash
# Sync a local directory
oikb sync ./docs --kb your-kb-id

# Sync a GitHub repo (no clone needed)
oikb sync github:owner/repo --kb your-kb-id

# Sync an S3 bucket
oikb sync s3://bucket/prefix --kb your-kb-id

# Preview changes without uploading
oikb diff ./docs --kb your-kb-id

# Watch for changes and auto-sync
oikb watch ./docs --kb your-kb-id

# List files in a KB
oikb ls --kb your-kb-id

# Show KB info
oikb status --kb your-kb-id

# Reset a KB
oikb reset --kb your-kb-id
```

### Sources

| Source | Syntax | Install |
|---|---|---|
| Local directory | `./docs`, `/path/to/dir` | included |
| GitHub repo | `github:owner/repo` | included |
| S3 bucket | `s3://bucket/prefix` | `pip install oikb[s3]` |

GitHub sources support `--branch` and `--path` filtering:

```bash
oikb sync github:owner/repo --kb your-kb-id --branch main --path docs/
```

## Configuration

Settings are resolved in this order (highest priority wins):

1. **CLI flags** (`--url`, `--token`)
2. **Environment variables** (`OPEN_WEBUI_URL`, `OPEN_WEBUI_API_KEY`)
3. **Config file** (`~/.config/oikb/config.yaml`)

```bash
oikb config set url http://localhost:3000
oikb config set token sk-your-api-key
oikb config get
```

## Declarative Config (`.oikb.yaml`)

For recurring multi-source syncs, place a `.oikb.yaml` in your project root:

```yaml
sync:
  - source: ./docs
    kb: project-docs

  - source: github:owner/wiki
    kb: team-wiki
    branch: main

  - source: s3://company-docs/engineering
    kb: eng-handbook
```

```bash
# Sync all entries
oikb sync

# Sync a specific entry
oikb sync --name project-docs
```

## `.oikbignore`

Place a `.oikbignore` file in your source directory to exclude files (gitignore-style):

```
dist/
build/
*.pyc
*.draft.*
*.zip
```

## Docker

The published image is available at `ghcr.io/open-webui/oikb`.

```bash
# One-shot sync
docker run --rm \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb sync /data --kb your-kb-id

# Watch mode (keep running)
docker run --rm -d \
  -e OPEN_WEBUI_URL=http://host.docker.internal:3000 \
  -e OPEN_WEBUI_API_KEY=sk-your-key \
  -v ./docs:/data \
  ghcr.io/open-webui/oikb watch /data --kb your-kb-id
```

### Docker Compose

Run as a sidecar alongside Open WebUI. Watches a mounted directory and auto-syncs:

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
    command: watch /data --kb ${KB_ID}
    depends_on:
      - open-webui
    restart: unless-stopped
```

### GitHub Actions

```yaml
- name: Sync docs to Open WebUI
  uses: docker://ghcr.io/open-webui/oikb:latest
  with:
    args: sync /github/workspace/docs --kb ${{ secrets.KB_ID }}
  env:
    OPEN_WEBUI_URL: ${{ secrets.OPEN_WEBUI_URL }}
    OPEN_WEBUI_API_KEY: ${{ secrets.OPEN_WEBUI_API_KEY }}
```

## How It Works

1. Scan source (local dir, GitHub, S3), compute SHA-256 checksums
2. Send manifest to Open WebUI's `/sync/diff` endpoint
3. Server diffs against stored file hashes
4. Delete stale files, create missing directories
5. Upload only new and modified files

## License

MIT. See [LICENSE](LICENSE) for details.
