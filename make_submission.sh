#!/usr/bin/env bash
# Build the CAT submission: source code + fresh database export in one zip.
# Usage: ./make_submission.sh 7    ->  ../Group7_Mboni_African_Film_Streaming.zip
set -euo pipefail
cd "$(dirname "$0")"
GROUP="${1:?Give your group number, e.g. ./make_submission.sh 7}"
python3 -m flask --app run export-db database/mboni.sql
OUT="../Group${GROUP}_Mboni_African_Film_Streaming.zip"
rm -f "$OUT"
zip -rq "$OUT" . -x '*__pycache__*' '*.pyc' '.git/*' 'instance/*'
echo "Created $(realpath "$OUT") ($(du -h "$OUT" | cut -f1))"
