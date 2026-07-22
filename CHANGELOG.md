# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/); versioning is [SemVer](https://semver.org/).

## [2.2.0] - 2026-07-22
### Added
- Session-based login **form** on the web UI (`WEB_USER`/`WEB_PASSWORD`/`WEB_SECRET`), password-manager friendly, defense-in-depth behind Cloudflare Access.
### Fixed
- Protect button no longer triggers the delete confirmation modal (confirm moved onto the delete action).

## [2.1.0] - 2026-07-22
### Added
- Flask web UI (`radarr-janitor-web`): configure sweeps, review candidates, protect films, and delete with an explicit confirm.
- Dockerfile + container deployment behind Cloudflare (`janitor.dangericke.com`).
- GitHub Actions: CI (ruff + pytest) and tag-triggered Release with version/tag verification.
- `scripts/bump_version.py` for SemVer bumps.
- Unit tests for the rules engine and OMDb parsing.

## [2.0.0] - 2026-07-22
### Added
- Multi-source scoring via OMDb (IMDb + Rotten Tomatoes + Metacritic) plus TMDb for genres/keywords.
- `report` (dry-run) / `apply` (approved deletes) split; deletion is never automatic.
- SQLite state (`janitor.db`): ratings cache, protected keep-list, run history, deletion audit.
- Seasonal (holiday) detection with re-download-friendly exclusion handling.
- Quota-aware OMDb usage (in-scope only, daily cap, persistent cache).
- Telegram notifications for the quarterly report.

### Changed
- Config now loads from `.env`; API keys removed from source.
- Replaced the `last_id` flat-file cursor with SQLite.

### Fixed
- Radarr v3 delete now uses `addImportExclusion` (the old `addExclusion` param was a no-op).
- Default Radarr URL points at the current host instead of the retired NAS address.

### Security
- Removed the hardcoded Radarr API key that was committed in `settings.py` (rotate the leaked key; it remains in pre-2.0 history).
