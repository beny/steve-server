#!/bin/bash
# Nainstaluje steve-server jako LaunchAgent: venv, závislosti, plist,
# start. KeepAlive ho drží při pádu, RunAtLoad nastartuje po přihlášení.
# Opakované spuštění = reinstalace (aktualizuje závislosti i plist).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="cz.steve.server"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT="${STEVE_PORT:-8000}"
PYTHON="${STEVE_PYTHON:-}"
if [ -z "$PYTHON" ]; then
    if [ -x /opt/homebrew/bin/python3 ]; then
        PYTHON=/opt/homebrew/bin/python3
    else
        PYTHON=python3
    fi
fi

echo "==> venv + závislosti"
[ -d "$ROOT/.venv" ] || "$PYTHON" -m venv "$ROOT/.venv"
"$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt"

mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"

echo "==> $PLIST"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$ROOT/.venv/bin/uvicorn</string>
        <string>app.main:app</string>
        <string>--host</string>
        <string>0.0.0.0</string>
        <string>--port</string>
        <string>$PORT</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$ROOT</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$ROOT/logs/server.log</string>
    <key>StandardErrorPath</key>
    <string>$ROOT/logs/server.log</string>
</dict>
</plist>
EOF

echo "==> (re)start"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"

for attempt in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf "http://localhost:$PORT/docs" > /dev/null; then
        echo "OK: server běží na portu $PORT (log: logs/server.log)"
        break
    fi
    if [ "$attempt" -eq 10 ]; then
        echo "POZOR: server neodpovídá — koukni do logs/server.log"
        exit 1
    fi
    sleep 1
done

cat <<'HINT'

Aby Mac mini v noci nespal (jednorázově, chce sudo):
    sudo pmset -a sleep 0

Odinstalace:
    launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/cz.steve.server.plist
    rm ~/Library/LaunchAgents/cz.steve.server.plist
HINT
