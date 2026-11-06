#!/usr/bin/env bash
# Promote a server-built artifact, retaining a dated rollback copy.
set -euo pipefail
ROOT="${PPCI_ROOT:-/opt/ppci}"
BUILD="${PPCI_BUILD_ROOT:-/opt/ppci-build}"
MODE="${1:?Usage: deploy-built.sh backend|kimi|frontend}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/var/backups/ppci/releases/$STAMP-$MODE"
mkdir -p "$BACKUP"
case "$MODE" in
  backend|kimi)
    if [[ "$MODE" == backend ]]; then
      REPO=secretpad; UNITS=(ppci-alice ppci-bob)
    else
      REPO=secretpad-kimi-upstream; UNITS=(ppci-kimi)
    fi
    SOURCE="$BUILD/$REPO/target/secretpad.jar"
    TARGET="$ROOT/NewProject/$REPO/target/secretpad.jar"
    test -s "$SOURCE"
    cp -p "$TARGET" "$BACKUP/secretpad.jar"
    cp -p "$SOURCE" "$TARGET.next"
    mv "$TARGET.next" "$TARGET"
    systemctl restart "${UNITS[@]}"
    ;;
  frontend)
    SOURCE="$BUILD/secretpad-frontend/apps/platform/dist"
    TARGET="$ROOT/NewProject/secretpad-frontend-dist-e2e"
    test -s "$SOURCE/index.html"
    cp -a "$TARGET" "$BACKUP/dist"
    # Preserve older hashed assets for browsers with an already-open page.
    rsync -a --exclude=index.html "$SOURCE/" "$TARGET/"
    cp -p "$SOURCE/index.html" "$TARGET/index.html.next"
    mv "$TARGET/index.html.next" "$TARGET/index.html"
    ;;
  *) echo 'Usage: deploy-built.sh backend|kimi|frontend' >&2; exit 2 ;;
esac
for i in $(seq 1 30); do
  if ppci-platform status > "$BACKUP/health.json" || /usr/bin/python3.11 -c '
import json, sys
try:
    data = json.load(open(sys.argv[1]))
except (OSError, ValueError):
    sys.exit(1)
sys.exit(0 if data.get("runtimeHealthy") is True else 1)
' "$BACKUP/health.json"; then
    echo "Deployed $MODE; rollback files: $BACKUP"
    exit 0
  fi
  sleep 2
done
echo "Health check failed; restoring $BACKUP" >&2
if [[ "$MODE" == frontend ]]; then
  rsync -a "$BACKUP/dist/" "$TARGET/"
else
  cp "$BACKUP/secretpad.jar" "$TARGET.rollback"
  mv "$TARGET.rollback" "$TARGET"
  systemctl restart "${UNITS[@]}"
fi
exit 1
