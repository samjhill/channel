#!/bin/bash
set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <SERVER_IP>"
    exit 1
fi

SERVER_IP="$1"
KODI_DIR="$HOME/.kodi/userdata/addon_data/pvr.iptvsimple"

mkdir -p "$KODI_DIR"

cat > "$KODI_DIR/settings.xml" <<EOF
<settings>
    <setting id="m3uUrl">http://$SERVER_IP:8080/channel/stream.m3u8</setting>
    <setting id="startNum">1</setting>
</settings>
EOF

echo "Configured IPTV Simple Client with $SERVER_IP"

