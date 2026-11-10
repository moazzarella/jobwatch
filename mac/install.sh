#!/bin/bash
# Installs jobwatch as a background job on this Mac (runs every 15 minutes while the Mac is awake).
# Usage:  bash mac/install.sh <TELEGRAM_BOT_TOKEN> <TELEGRAM_CHAT_ID> [sources]
#   sources defaults to "mostaql" (the site most likely to block GitHub's servers).
set -euo pipefail

TOKEN="${1:?bot token required}"
CHAT="${2:?chat id required}"
SOURCES="${3:-mostaql}"
DIR="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.moaaz.jobwatch"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$(command -v python3)"

mkdir -p "$HOME/Library/LaunchAgents" "$DIR/mac/logs"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>$DIR/jobwatch.py</string></array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>TELEGRAM_BOT_TOKEN</key><string>$TOKEN</string>
    <key>TELEGRAM_CHAT_ID</key><string>$CHAT</string>
    <key>JOBWATCH_SOURCES</key><string>$SOURCES</string>
    <key>JOBWATCH_RUNNER</key><string>Mac</string>
    <key>JOBWATCH_STATE</key><string>$DIR/mac/state.json</string>
  </dict>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$DIR/mac/logs/jobwatch.log</string>
  <key>StandardErrorPath</key><string>$DIR/mac/logs/jobwatch.log</string>
</dict>
</plist>
EOF
chmod 600 "$PLIST"   # the file holds your bot token; keep it private

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Installed. Watching: $SOURCES. Log: $DIR/mac/logs/jobwatch.log"
echo "To stop it:  launchctl bootout gui/\$(id -u)/$LABEL"
