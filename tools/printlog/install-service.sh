#!/bin/sh
# Run printlog-server as a systemd --user service on this machine (the box
# that keeps the print history; usually the same one as openscad-server).
# Needs `loginctl enable-linger $USER` once so it starts at boot without a
# login. Re-run after moving the checkout.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR" "$HOME/.config/printlog"
cat > "$UNIT_DIR/printlog-server.service" <<UNIT
[Unit]
Description=3D print history (printlog)
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 $HERE/server.py
Environment=HOME=$HOME
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now printlog-server.service
systemctl --user restart printlog-server.service
sleep 1
systemctl --user --no-pager --lines=5 status printlog-server.service || true
echo
echo "token for clients: $(cat "$HOME/.config/printlog/token" 2>/dev/null || echo '(not yet generated; check again in a moment)')"
echo "history page:      http://$(hostname):$(python3 -c "import json,os;p=os.path.expanduser('~/.config/printlog/config.json');print(json.load(open(p)).get('port',8791) if os.path.exists(p) else 8791)")/"
