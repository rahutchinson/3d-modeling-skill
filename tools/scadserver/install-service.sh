#!/bin/sh
# Run openscad-server as a systemd --user service on this machine (the
# render box). Needs `loginctl enable-linger $USER` once so it starts at
# boot without a login. Re-run after moving the checkout.
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR" "$HOME/.config/openscad-server"
cat > "$UNIT_DIR/openscad-server.service" <<EOF
[Unit]
Description=OpenSCAD render server (rscad)
After=network-online.target

[Service]
ExecStart=/usr/bin/python3 $HERE/server.py
Environment=HOME=$HOME
Environment=PATH=$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin
Restart=on-failure
RestartSec=5
Nice=5

[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
systemctl --user enable --now openscad-server.service
sleep 1
systemctl --user --no-pager --lines=5 status openscad-server.service || true
echo
echo "token for clients: $(cat "$HOME/.config/openscad-server/token" 2>/dev/null || echo '(not yet generated; check again in a moment)')"
echo "status page:       http://$(hostname):$(python3 -c "import json,os;p=os.path.expanduser('~/.config/openscad-server/config.json');print(json.load(open(p)).get('port',8790) if os.path.exists(p) else 8790)")/"
