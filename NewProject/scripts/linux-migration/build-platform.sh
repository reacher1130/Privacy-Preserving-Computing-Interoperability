#!/usr/bin/env bash
# Compile in a separate server workspace; never overwrite a running release.
set -euo pipefail
ROOT="${PPCI_SOURCE_ROOT:-${PPCI_ROOT:-/opt/ppci-source}}"
BUILD="${PPCI_BUILD_ROOT:-/opt/ppci-build}"
MODE="${1:-backend}"
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-21-openjdk}"
export PATH="/opt/ppci-tools/node20/bin:/opt/ppci-tools/maven/bin:/opt/ppci-tools/pnpm8/node_modules/.bin:$JAVA_HOME/bin:$PATH"
export MAVEN_OPTS="${MAVEN_OPTS:--Xmx2g -XX:ActiveProcessorCount=2}"
case "$MODE" in
  backend) SOURCE=secretpad ;;
  kimi) SOURCE=secretpad-kimi-upstream ;;
  frontend) SOURCE=secretpad-frontend ;;
  *) echo 'Usage: build-platform.sh [backend|kimi|frontend]' >&2; exit 2 ;;
esac
MARKER=pom.xml
[[ "$MODE" != frontend ]] || MARKER=package.json
[[ -f "$ROOT/NewProject/$SOURCE/$MARKER" ]] || { echo "Incomplete Git source checkout: $SOURCE/$MARKER" >&2; exit 2; }
mkdir -p "$BUILD/$SOURCE"
rsync -a --delete --no-owner --no-group --exclude=node_modules --exclude=target \
  --exclude=/logs --exclude=/log --exclude='/db*' --exclude='/data*' \
  --exclude=dist --exclude=.cache --exclude=.local-backups \
  "$ROOT/NewProject/$SOURCE/" "$BUILD/$SOURCE/"
cd "$BUILD/$SOURCE"
if [[ "$MODE" == frontend ]]; then
  export NODE_OPTIONS=--max-old-space-size=3072
  pnpm install --frozen-lockfile
  pnpm --filter @secretflow/utils build
  pnpm --filter @secretflow/dag build
  pnpm --filter secretpad build:demo
else
  mvn -B -Dmaven.repo.local="$BUILD/.m2" -DskipTests -Dfile.encoding=UTF-8 package
fi
printf 'Build output: %s/%s\n' "$BUILD" "$SOURCE"
