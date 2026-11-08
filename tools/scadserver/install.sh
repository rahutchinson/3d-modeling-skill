#!/bin/sh
# Install the rscad client on this machine and point it at the server that
# served this script. Usage (TOKEN is in ~/.config/openscad-server/token on
# the server):
#
#   curl -sf http://SERVER:8790/install.sh | sh -s -- TOKEN
#
# Add --as-openscad to also link ~/.local/bin/openscad -> rscad so every
# Makefile uses the server without setting OPENSCAD=rscad.
set -eu
BASE="${RSCAD_URL:-@BASE_URL@}"
TOKEN=""; AS_OPENSCAD=0
for a in "$@"; do
  case "$a" in
    --as-openscad) AS_OPENSCAD=1 ;;
    *) TOKEN="$a" ;;
  esac
done
[ -n "$TOKEN" ] || { echo "usage: install.sh TOKEN [--as-openscad]" >&2; exit 1; }

BIN="$HOME/.local/bin"; CFG="$HOME/.config/rscad"
mkdir -p "$BIN" "$CFG"
curl -sf "$BASE/rscad" -o "$BIN/rscad" || { echo "could not fetch $BASE/rscad" >&2; exit 1; }
chmod +x "$BIN/rscad"
printf '%s\n' "$BASE" > "$CFG/url"
printf '%s\n' "$TOKEN" > "$CFG/token"; chmod 600 "$CFG/token"

if [ "$AS_OPENSCAD" = 1 ]; then
  if [ -e "$BIN/openscad" ] && [ ! -L "$BIN/openscad" ]; then
    echo "not replacing the existing $BIN/openscad (a real binary); use OPENSCAD=rscad instead" >&2
  else
    ln -sf rscad "$BIN/openscad"
    echo "linked $BIN/openscad -> rscad"
  fi
fi

echo "installed $BIN/rscad -> $BASE"
case ":$PATH:" in *":$BIN:"*) ;; *) echo "note: $BIN is not on PATH" ;; esac
"$BIN/rscad" --rscad-status || echo "server not reachable right now" >&2
