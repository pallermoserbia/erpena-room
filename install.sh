#!/bin/bash
# Instalacija na Raspberry Pi OS (Lite): sudo bash install.sh
set -e
apt-get update
apt-get install -y ffmpeg python3-requests alsa-utils
id erpena-room >/dev/null 2>&1 || useradd --system --home /var/lib/erpena-room --groups audio erpena-room
install -d -o erpena-room -g erpena-room /opt/erpena-room /etc/erpena-room /var/lib/erpena-room
install -m 755 agent.py /opt/erpena-room/agent.py
install -m 644 erpena-room.service /etc/systemd/system/erpena-room.service
systemctl daemon-reload
if systemctl is-enabled --quiet erpena-room 2>/dev/null; then systemctl restart erpena-room; echo "Servis je azuriran i restartovan."; fi
echo
echo "Gotovo. Sledeci koraci:"
echo "  1) U Erpeni: Sastanci > Sale > Dodaj uredjaj, kopiraj kod"
echo "  2) sudo -u erpena-room python3 /opt/erpena-room/agent.py mics        (nadji mikrofon)"
echo "  3) sudo -u erpena-room python3 /opt/erpena-room/agent.py pair --url https://VASA-FIRMA.erpena.rs --code KOD --alsa plughw:1,0"
echo "  4) sudo -u erpena-room python3 /opt/erpena-room/agent.py test         (proveri zvuk)"
echo "  5) sudo systemctl enable --now erpena-room"
