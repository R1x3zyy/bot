#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/gemini-store}"

cd "$APP_DIR"

git fetch --all --prune
git reset --hard origin/main

"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
"$APP_DIR/.venv/bin/python" -m py_compile "$APP_DIR/bot.py" "$APP_DIR/db.py" "$APP_DIR/admin.py"

cd "$APP_DIR/admin_frontend"
npm install
npm run build

chown -R gemini:gemini "$APP_DIR"
chmod 600 "$APP_DIR/.env"

systemctl restart gemini-api.service
systemctl restart gemini-bot.service
systemctl reload nginx

systemctl is-active --quiet gemini-api.service
systemctl is-active --quiet gemini-bot.service
