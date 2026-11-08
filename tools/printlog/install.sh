#!/bin/sh
# Install the printlog client on this machine and point it at the server
# that served this script. Usage (TOKEN is ~/.config/printlog/token on the
# server; it is the same as the openscad-server token when both run there):
#
#   curl -sf http://SERVER:8791/install.sh | sh -s -- TOKEN
set -eu
BASE="${PRINTLOG_URL:-@BASE_URL@}"
TOKEN="${1:-}"
[ -n "$TOKEN" ] || { echo "usage: install.sh TOKEN" >&2; exit 1; }
BIN="$HOME/.local/bin"; CFG="$HOME/.config/printlog"
mkdir -p "$BIN" "$CFG"
curl -sf "$BASE/printlog" -o "$BIN/printlog" || { echo "could not fetch $BASE/printlog" >&2; exit 1; }
chmod +x "$BIN/printlog"
printf '%s\n' "$BASE" > "$CFG/url"
printf '%s\n' "$TOKEN" > "$CFG/token"; chmod 600 "$CFG/token"
echo "installed $BIN/printlog -> $BASE"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "note: $BIN is not on PATH" ;; esac
"$BIN/printlog" server || echo "server not reachable right now" >&2
