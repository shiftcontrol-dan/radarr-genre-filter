#!/usr/bin/env bash
# Quarterly candidate report + Telegram summary (no deletion).
# Install in artagel's crontab, e.g. 09:00 on the 1st of Jan/Apr/Jul/Oct:
#   0 9 1 1,4,7,10 * /home/artagel/radarr-genre-filter/deploy/quarterly-report.sh >> /home/artagel/radarr-genre-filter/quarterly.log 2>&1
set -euo pipefail
cd /home/artagel/radarr-genre-filter
./.venv/bin/radarr-janitor report --seasonal --notify
