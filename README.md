# radarr-janitor (formerly radarr-genre-filter)

Score-aware, AI-assisted cleanup for a Radarr library. Sweep by genre, threshold on
**multiple rating sources** (IMDb + Rotten Tomatoes + Metacritic via OMDb), prune
**seasonal** pile-up (holiday movies), and never blow away a cult classic by accident.

Nothing is deleted automatically: `report` builds a candidate list, you (or the
companion **MediaJanitor** skill) approve, and `apply` executes.

## What changed from v1

- **Multi-source scoring.** Old version used only TMDb's vote average, which would have
  deleted things like *28 Days Later*. Now uses IMDb / Rotten Tomatoes / Metacritic.
- **Report/apply split.** Deletion is a separate, explicit step against an approved list.
- **SQLite state** (`janitor.db`) replaces the `last_id` flat file: ratings cache
  (respects OMDb's daily limit), a protected **keep-list**, run history, and a deletion audit.
- **Seasonal pruning** with smart exclusion: holiday movies are removed but allowed to
  re-download next year; low-score junk is excluded (blacklisted) so it stays gone.
- **Config via `.env`** (no more API keys in source).
- Fixed: Radarr v3 delete now uses `addImportExclusion` (the old `addExclusion` was a no-op),
  and the default Radarr URL is the current host.

## Install

```bash
pip install -e .          # or: pip install -r requirements.txt
cp .env.example .env      # then fill in RADARR_API_KEY and OMDB_API_KEY
```

Get a free OMDb key at https://www.omdbapi.com/apikey.aspx.

## Usage

```bash
# What genres are in my library?
radarr-janitor list-genres

# Build a candidate report (no deletion): horror sweep + low multi-source scores
radarr-janitor report --filter Horror --imdb-below 5.5 --rt-below 40

# Seasonal pile-up
radarr-janitor report --seasonal

# Protect a cult classic so it's never flagged again
radarr-janitor keep add --tmdb 170 --title "28 Days Later" --reason "cult horror landmark, launched a franchise"

# Delete from the latest report (interactive confirm; only 'remove' verdicts)
radarr-janitor apply

# Delete from an AI/human-approved decisions file
radarr-janitor apply --from-json reports/report-12.approved.json --yes
```

Old command still works (mapped to a safe report):

```bash
python3 run_radarr_filter.py --filter Horror --deletefile --addexclusion --minscore 85
```

## Verdicts

- `remove` — a score threshold was crossed; a clear cut.
- `review` — matched a genre/seasonal sweep but scores aren't clearly bad. The MediaJanitor
  skill's AI layer decides keep vs remove here (the cult-classic rescue path).
- `keep` — on the protected keep-list; never deleted.

## Quarterly automation

A cron on docker01 runs `report --seasonal --notify`, which builds the candidate list and
sends a **Telegram** summary. You then run the MediaJanitor skill to apply AI judgment and
approve deletions. See `deploy/` for the cron unit.

## License

MIT
