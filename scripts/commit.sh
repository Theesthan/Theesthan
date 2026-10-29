#!/usr/bin/env bash
# Commits the regenerated assets and pushes.
# RUN=morning always commits. RUN=evening commits half the time when today
# already has a commit (always if the morning run was dropped) -> 1 or 2 commits/day.
set -euo pipefail
today=$(date -u +%F)
last=$(TZ=UTC git log -1 --date=format-local:%F --format=%cd 2>/dev/null || true)
if [ "${RUN:-morning}" = "evening" ] && [ "$last" = "$today" ] && [ $((RANDOM % 2)) -eq 0 ]; then
  echo "skip: already committed today"
  exit 0
fi
git add assets
git commit -q -m "chore: refresh player card"
git push -q origin HEAD
