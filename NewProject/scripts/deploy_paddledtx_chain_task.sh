#!/usr/bin/env bash
# Publish the independently built manager and native UI together. Old container and assets remain.
set -euo pipefail
umask 077
[[ $(id -u) == 0 ]]
manager=${PPCI_DTX_MANAGER_CONTAINER:-ppci-dtx-manager}
native=${PPCI_DTX_NATIVE_ROOT:-/opt/ppci/privacy-computing-interconnectivity/shared-exchange-Connectivity/dtx-fe}
index=static/unicom-dtx/page/index.html
state=${PPCI_DTX_STATE_ROOT:-/srv/ppci/dtx-manager}
base=${PPCI_DTX_BASE_URL:-http://192.168.45.101:18511}
buildRoot=${PPCI_DTX_BUILD_ROOT:-/opt/ppci-build}
releaseRoot=${PPCI_DTX_RELEASE_ROOT:-/var/backups/ppci/releases}
chainNetwork=${PPCI_DTX_CHAIN_NETWORK:-ppci-blockchain-network}
dbNetwork=${PPCI_DTX_DB_NETWORK:-mysql_default}
uiContainer=${PPCI_DTX_UI_CONTAINER:-paddledtx-native-e2e}
hostPort=${PPCI_DTX_MANAGER_HOST_PORT:-8084}
containerPort=${PPCI_DTX_MANAGER_CONTAINER_PORT:-8488}
adminCredentials=${PPCI_DTX_ADMIN_CREDENTIALS:-$state/private/credentials.json}
probeCredentials=${PPCI_DTX_PROBE_CREDENTIALS:-$state/private/probe-credentials.json}
executors=${PPCI_DTX_EXPECTED_EXECUTORS:-executor1,executor2}
buildRoot=$(realpath "$buildRoot")
releaseRoot=$(realpath "$releaseRoot")
exec 9>"$buildRoot/.dtx-chain-task-release.lock"
flock -n 9

if [[ ${1:-} == rollback ]]; then
  release=$(realpath "${2:?rollback release directory required}")
  [[ "$release" == "$releaseRoot/"*-dtx-chain-task.* ]]
  [[ -f "$release/previous-index.html" && -f "$release/frontend.patch" ]]
  read -r old <"$release/previous-container"
  read -r new <"$release/new-container"
  [[ $(docker inspect -f '{{.Id}}' "$manager") == "$new" ]]
  docker inspect "$old" >/dev/null
  cp -p "$release/previous-index.html" "$native/build/$index.rollback"
  mv -f "$native/build/$index.rollback" "$native/build/$index"
  if (cd "$native" && git apply --reverse --check "$release/frontend.patch"); then
    (cd "$native" && git apply --reverse "$release/frontend.patch")
  fi
  docker stop -t 15 "$manager" >/dev/null
  docker rename "$manager" "$manager-reverted-${new:0:12}"
  docker rename "$old" "$manager"
  docker start "$manager" >/dev/null
  printf 'previous_manager_restored=%s\n' "$old"
  exit
fi

[[ ${1:-} == publish && $# == 6 ]] || {
  echo "Usage: $0 publish MANAGER_STAGE UI_STAGE OLD_CONTAINER_ID CANDIDATE_IMAGE_ID VALIDATION_TASK_UUID" >&2
  echo "       $0 rollback RELEASE_DIRECTORY" >&2
  exit 2
}
stage=$(realpath "$2")
ui=$(realpath "$3")
old=$4
image=$5
task=$6
[[ "$stage" == "$buildRoot/".stage-dtx-manager-chain-task.* && "$ui" == "$buildRoot/"dtx-native-chain-task.* ]]
[[ "$task" =~ ^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$ ]]
[[ $(docker inspect -f '{{.Id}}' "$manager") == "$old" ]]
[[ $(docker inspect -f '{{.State.Running}}' "$manager") == true ]]
[[ $(docker image inspect --format '{{.Id}}' "$image") == "$image" ]]
[[ $(docker inspect -f '{{.HostConfig.NetworkMode}}' "$manager") == "$chainNetwork" ]]
docker inspect -f '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}}{{"\n"}}{{end}}' "$manager" | grep -Fxq "$dbNetwork"
[[ -x "$stage/check" && -s "$stage/manager.patch" && -s "$ui/chain-task.patch" ]]
grep -Fq 'window.__DTX_DEMO_AUTH_DISABLED__ = false;' "$ui/build/$index"
(cd "$native" && git apply --check "$ui/chain-task.patch")
cmp "$native/src/public/index.html" "$ui/src/public/index.html"
oldIndex=$(sha256sum "$native/build/$index" | cut -d' ' -f1)
[[ "$oldIndex" == "$(curl -fsS --max-time 5 "$base/dtx/console/" | sha256sum | cut -d' ' -f1)" ]]
[[ "$oldIndex" == "$(cat "$ui/live-index.sha256")" ]]
[[ "$(sha256sum "$ui/build/$index" | cut -d' ' -f1)" == "$(cat "$ui/candidate-index.sha256")" ]]
(cd "$ui/build" && find . -type f -print0 | sort -z | xargs -0 sha256sum) > "$stage/ui-candidate.sha256"

# Preserve the existing container and bind mounts. The candidate reads the same database with schema sync disabled.
release=$(mktemp -d "$releaseRoot/$(date +%Y%m%d-%H%M%S)-dtx-chain-task.XXXXXXXX")
printf 'release=%s\n' "$release"
install -m 0700 "$0" "$release/deploy.sh"
cp -p "$native/build/$index" "$release/previous-index.html"
cp -p "$ui/chain-task.patch" "$release/frontend.patch"
cp -p "$stage/manager.patch" "$release/manager.patch"
printf '%s\n' "$old" > "$release/previous-container"
"$stage/check" -chain-baseline -base-url "$base" -credentials "$adminCredentials" > "$release/manager-before.json"
mountSource() {
  docker inspect -f '{{range .Mounts}}{{if eq .Destination "/home/'"$1"'"}}{{if eq .Type "bind"}}{{.Source}}{{end}}{{end}}{{end}}' "$old"
}
liveConf=$(mountSource conf)
[[ -d "$liveConf" && -f "$liveConf/app.conf" ]]
cp -a "$liveConf" "$release/conf"
sed -i -E 's/^runSyncdb[[:space:]]*=[[:space:]]*true[[:space:]]*$/runSyncdb = false/' "$release/conf/app.conf"
grep -Fxq 'runSyncdb = false' "$release/conf/app.conf"
if [[ -n ${PPCI_DTX_REQUESTER_PUBLIC_KEY_FILE:-} ]]; then
  PPCI_CHAIN_TASK_REQUESTER=$(tr -d '\r\n' < "$PPCI_DTX_REQUESTER_PUBLIC_KEY_FILE")
else
  PPCI_CHAIN_TASK_REQUESTER=$(docker exec "${PPCI_DTX_REQUESTER_CONTAINER:-executor1.node.com}" cat /home/reqkeys/public.key | tr -d '\r\n')
fi
[[ "$PPCI_CHAIN_TASK_REQUESTER" =~ ^[0-9a-f]{128}$ ]]
export PPCI_CHAIN_TASK_REQUESTER
gateway=${PPCI_DTX_MANAGER_GATEWAY:-}
if [[ -z "$gateway" ]]; then
  gateway=$(docker exec "$uiContainer" getent hosts host.docker.internal | awk 'NR==1 {print $1}')
fi
[[ "$gateway" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
declare -a binds
for dir in log data upload; do
  actual=$(mountSource "$dir")
  [[ -d "$actual" ]]
  binds+=(-v "$actual:/home/$dir:rw")
done
oldName="$manager-backup-${old:0:12}"
candidateName="$manager-next-$(basename "$release" | awk -F. '{print $NF}')"
new=$(docker create --name "$candidateName" --network "$chainNetwork" \
  --restart unless-stopped --read-only --cap-drop ALL --security-opt no-new-privileges \
  --memory 512m --cpus 2 -e GOMAXPROCS=2 -e PPCI_CHAIN_TASK_REQUESTER \
  --tmpfs /tmp:rw,nosuid,noexec,size=16m \
  -p "127.0.0.1:$hostPort:$containerPort" -p "$gateway:$hostPort:$containerPort" \
  -v "$release/conf:/home/conf:ro" "${binds[@]}" "$image")
printf '%s\n' "$new" > "$release/new-container"
docker network connect "$dbNetwork" "$new"
sourceApplied=0
indexSwapped=0
oldStopped=0
rollback_on_failure() {
  rc=$?
  if (( rc == 0 )); then return; fi
  set +e
  if (( indexSwapped )); then
    cp -p "$release/previous-index.html" "$native/build/$index.rollback"
    mv -f "$native/build/$index.rollback" "$native/build/$index"
  fi
  if (( sourceApplied )); then
    (cd "$native" && git apply --reverse --check "$release/frontend.patch" && git apply --reverse "$release/frontend.patch")
  fi
  docker stop -t 15 "$new" >/dev/null 2>&1
  if [[ $(docker inspect -f '{{.Name}}' "$new") == "/$manager" ]]; then
    docker rename "$new" "$candidateName"
  fi
  if (( oldStopped )); then
    if [[ $(docker inspect -f '{{.Name}}' "$old") == "/$oldName" ]]; then docker rename "$old" "$manager"; fi
    docker start "$old" >/dev/null
  fi
  echo "Release failed; previous manager restored. Retained artifacts: $release" >&2
}
trap rollback_on_failure EXIT
oldStopped=1
docker stop -t 15 "$old" >/dev/null
docker rename "$old" "$oldName"
docker rename "$new" "$manager"
docker start "$new" >/dev/null
for attempt in $(seq 1 20); do
  if curl -fsS --max-time 2 "$base/dtx/v1/task/chain-detail?chainTaskId=$task" | grep -Fq '"code":"SignErr"'; then break; fi
  [[ $attempt != 20 ]]
  sleep 1
done
"$stage/check" -chain-task-id "$task" -credentials "$adminCredentials" -probe-credentials "$probeCredentials" \
  -base-url "$base" -expected-executors "$executors" > "$release/chain-task-verification.json"
python3 - "$release" <<'PY'
import json
from pathlib import Path
import sys
p = Path(sys.argv[1])
a, b = [json.loads((p / f).read_text()) for f in ("manager-before.json", "chain-task-verification.json")]
assert a["pass"] and b["pass"] and a["list_totals"] == b["list_totals"]
print(json.dumps(b, ensure_ascii=False))
PY
(cd "$native" && git apply "$release/frontend.patch")
sourceApplied=1
rsync -a --chmod=D755,F644 --exclude="/$index" "$ui/build/" "$native/build/"
install -m 0644 "$ui/build/$index" "$native/build/$index.next"
indexSwapped=1
mv -f "$native/build/$index.next" "$native/build/$index"
(cd "$native/build" && sha256sum -c --status "$stage/ui-candidate.sha256")
[[ $(curl -fsS --max-time 8 "$base/dtx/console/" | sha256sum | cut -d' ' -f1) == "$(sha256sum "$ui/build/$index" | cut -d' ' -f1)" ]]
printf 'released=true previous_container_retained=%s\n' "$oldName"
