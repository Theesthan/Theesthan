#!/usr/bin/env bash
# Runs commit.sh against a throwaway repo + bare remote. Exit 0 = pass.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git init -q --bare "$tmp/remote.git"
git clone -q "$tmp/remote.git" "$tmp/work" 2>/dev/null
cd "$tmp/work"
git config user.name t && git config user.email t@t && git config core.autocrlf false
mkdir assets
count() { git rev-list --count HEAD 2>/dev/null || echo 0; }
run() { echo "$RANDOM$RANDOM" > assets/card.svg; RUN=$1 bash "$here/commit.sh" >/dev/null; }

# evening run with no commit today must still commit (morning run was dropped)
run evening
[ "$(count)" -eq 1 ] || { echo "FAIL: evening without a commit today did not commit"; exit 1; }

# morning always commits
run morning
[ "$(count)" -eq 2 ] || { echo "FAIL: morning did not commit"; exit 1; }

# evening after a commit today: ~50/50, so 20 tries must see both outcomes
for _ in $(seq 20); do run evening; done
n=$(count)
[ "$n" -gt 2 ] && [ "$n" -lt 22 ] || { echo "FAIL: evening not random ($n commits)"; exit 1; }
[ "$(git --git-dir="$tmp/remote.git" rev-list --count --all)" -eq "$n" ] || { echo "FAIL: commits not pushed"; exit 1; }
echo "PASS ($n commits)"
