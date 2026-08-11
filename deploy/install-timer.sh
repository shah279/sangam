#!/usr/bin/env bash
# Installs/updates the Sangam systemd timer from the repo's unit files.
# Run on the AWS box after editing sangam-ingest.service paths: bash deploy/install-timer.sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$here/sangam-ingest.service" "$here/sangam-ingest.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sangam-ingest.timer
echo "Installed. Next scheduled run:"
systemctl list-timers sangam-ingest.timer --no-pager
