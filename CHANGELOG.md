# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - Unreleased

### Added

- 🎉 **Initial release** of oikb, a CLI tool for syncing content to Open WebUI Knowledge Bases.
- 🔄 **Incremental sync** (`oikb sync`) — SHA-256 diffing uploads only new and modified files. Supports local directories, GitHub repos, and S3 buckets.
- 👀 **Dry-run preview** (`oikb diff`) — see what would change without uploading.
- 👁️ **Watch mode** (`oikb watch`) — auto-sync on file changes via watchdog with configurable debounce.
- 📋 **List files** (`oikb ls`) — list files in a Knowledge Base.
- ℹ️ **Status** (`oikb status`) — show KB info, file count, and total size.
- 🗑️ **Reset** (`oikb reset`) — delete all files in a Knowledge Base.
- ⚙️ **Configuration** (`oikb config`) — manage URL and API key via config file, env vars (`OPEN_WEBUI_URL`, `OPEN_WEBUI_API_KEY`), or CLI flags.
- 📁 **Declarative config** (`.oikb.yaml`) — multi-source sync from a single project file. `oikb sync` with no args reads it automatically.
- 🙈 **Ignore patterns** (`.oikbignore`) — gitignore-style file exclusion for local directory syncs.
- 🐙 **GitHub connector** (`github:owner/repo`) — sync via GitHub Trees API using blob SHAs as checksums. No local clone needed. Branch and path filtering supported.
- ☁️ **S3 connector** (`s3://bucket/prefix`) — sync via boto3 using ETags as checksums. Paginated listing for large buckets.
- 🐳 **Docker image** — multi-stage build with multi-arch support (amd64 + arm64). Mount source at `/data`, entrypoint is `oikb`.
- 🚀 **CI/CD** — GitHub Actions workflows for automated Docker image builds (GHCR) and GitHub Releases with changelog extraction.
