#!/usr/bin/env bash
# Pull new commits from GitHub, test them, and go live only if every test passes.
# Runs every 2 minutes from mboni-update.timer on the server.
set -uo pipefail
APP="${MBONI_DIR:-$HOME/srv/mboni}"
cd "$APP" || exit 1
git fetch -q origin main || exit 0           # offline: try again next time
current=$(git rev-parse HEAD)
latest=$(git rev-parse origin/main)
[ "$current" = "$latest" ] && exit 0

echo "$(date '+%F %T') new commit ${latest:0:7}: testing"
git checkout -q --detach "$latest"
python3 -m pip install -q --user -r requirements.txt >/dev/null 2>&1 || true
if python3 -m unittest -q >/tmp/mboni-tests.log 2>&1; then
  git checkout -q -B main "$latest"
  systemctl --user restart mboni.service
  echo "$(date '+%F %T') deployed ${latest:0:7}"
else
  git checkout -q main                       # back to the version that works
  echo "$(date '+%F %T') tests FAILED for ${latest:0:7}, still serving ${current:0:7}"
  tail -20 /tmp/mboni-tests.log
fi
