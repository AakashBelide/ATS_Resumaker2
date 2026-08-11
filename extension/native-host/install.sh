#!/usr/bin/env bash
# Register the ATS Resumaker native messaging host so the extension can run the CLI.
# Usage:  ./install.sh <extension-id>
# Get <extension-id> from chrome://extensions after "Load unpacked" (the ID under the name).
set -euo pipefail

EXT_ID="${1:-}"
if [ -z "$EXT_ID" ]; then
  echo "usage: ./install.sh <extension-id>"
  echo "  (copy the ID from chrome://extensions after loading the unpacked extension)"
  exit 1
fi

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOST="$DIR/resumaker_host.py"
NAME="com.resumaker.host"
chmod +x "$HOST"

MANIFEST="$(sed -e "s#__HOST_PATH__#$HOST#" -e "s#__EXTENSION_ID__#$EXT_ID#" "$DIR/$NAME.json")"

if [ "$(uname)" = "Darwin" ]; then
  BASE="$HOME/Library/Application Support"
  TARGETS=(
    "$BASE/Google/Chrome/NativeMessagingHosts"
    "$BASE/Microsoft Edge/NativeMessagingHosts"
    "$BASE/BraveSoftware/Brave-Browser/NativeMessagingHosts"
    "$BASE/Chromium/NativeMessagingHosts"
  )
else
  BASE="$HOME/.config"
  TARGETS=(
    "$BASE/google-chrome/NativeMessagingHosts"
    "$BASE/microsoft-edge/NativeMessagingHosts"
    "$BASE/BraveSoftware/Brave-Browser/NativeMessagingHosts"
    "$BASE/chromium/NativeMessagingHosts"
  )
fi

installed=0
for t in "${TARGETS[@]}"; do
  if [ -d "$(dirname "$t")" ]; then          # browser profile exists
    mkdir -p "$t"
    printf '%s\n' "$MANIFEST" > "$t/$NAME.json"
    echo "installed -> $t/$NAME.json"
    installed=1
  fi
done

if [ "$installed" = 1 ]; then
  echo "done — reload the extension, then use CLI or Auto mode."
else
  echo "no supported browser profile found (Chrome/Edge/Brave/Chromium). Open the browser once, then re-run."
fi
