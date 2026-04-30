#!/usr/bin/env bash
# Stop + unload the crawler daemon. Leaves logs and corpus alone.

set -euo pipefail

LABEL="np.gemma-god.crawler"
PLIST_DEST="$HOME/Library/LaunchAgents/${LABEL}.plist"

echo "[uninstall] stopping $LABEL"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [ -f "$PLIST_DEST" ]; then
    rm "$PLIST_DEST"
    echo "[uninstall] removed $PLIST_DEST"
else
    echo "[uninstall] no plist at $PLIST_DEST (already gone)"
fi

echo "[uninstall] done. Logs + corpus left in place."
