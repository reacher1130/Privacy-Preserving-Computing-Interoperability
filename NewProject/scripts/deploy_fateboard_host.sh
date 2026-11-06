#!/usr/bin/env bash
# Install an independent Host Board using a prepared, patched Guest Board JAR.
set -euo pipefail
umask 077

guest=${PPCI_FATE_GUEST_BOARD_CONTAINER:-fateboard-native-e2e}
host_flow=${PPCI_FATE_HOST_FLOW_CONTAINER:-fate2-flow-host-e2e}
host_flow_port=${PPCI_FATE_HOST_FLOW_PORT:-9380}
board=${PPCI_FATE_HOST_BOARD_CONTAINER:-fateboard-host-native-e2e}
network=${PPCI_FATE_HOST_BOARD_NETWORK:-ppci-bridge}
home=/data/projects/fate/fateboard
java=/data/projects/fate/env/jdk/jdk-8u345/bin
state=${PPCI_FATE_HOST_BOARD_STATE_DIR:-/var/lib/ppci/fateboard-host}
jar=fateboard-2.1.0.jar
expected_jar=${PPCI_FATE_BOARD_JAR_SHA256:-fa5a5a0aa9047cd9cd89d5396a2e0808d157fd5effe6fc929b14367a2a9bd1ea}
label=io.ppci.fateboard-role
bind_address=${PPCI_FATE_HOST_BOARD_BIND:-127.0.0.1}
board_port=${PPCI_FATE_HOST_BOARD_PORT:-19384}
bind=$bind_address:$board_port
flow_url=http://$host_flow:$host_flow_port
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

owns_board() {
    [[ $(docker inspect -f '{{index .Config.Labels "io.ppci.fateboard-role"}}' "$board") == host ]]
}

usage() {
    echo "Usage: $0 install|verify [JOB_ID HOST_PARTY_ID PSI_ROWS [GUEST_PARTY_ID]] or $0 rollback" >&2
    exit 2
}

action=${1:-}
case "$action" in
    install|verify|rollback) ;;
    *) usage ;;
esac
shift
task=()
if [[ $# != 0 ]]; then
    [[ $action != rollback && ( $# == 3 || $# == 4 ) ]] || usage
    [[ $1 =~ ^[[:alnum:]_-]+$ && $2 =~ ^[[:alnum:]_-]+$ && $3 =~ ^[0-9]+$ ]] || usage
    task=("$1" host "$2" "$3")
    if [[ $# == 4 ]]; then
        [[ $4 =~ ^[[:alnum:]_-]+$ ]] || usage
        task+=("$4")
    fi
fi
for value in "$guest" "$host_flow" "$board" "$network"; do
    [[ $value =~ ^[a-zA-Z0-9][a-zA-Z0-9_.-]*$ ]] || usage
done
[[ $board != "$guest" && $board != "$host_flow" && $state == /* && $state != *:* ]] || usage
[[ $expected_jar =~ ^[a-fA-F0-9]{64}$ ]] || usage
for port in "$board_port" "$host_flow_port"; do
    [[ $port =~ ^[1-9][0-9]{0,4}$ ]] && (( port <= 65535 )) || usage
done
python3 -c 'import ipaddress, sys; ip = ipaddress.IPv4Address(sys.argv[1]); sys.exit(not (ip.is_loopback or any(ip in ipaddress.IPv4Network(net) for net in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))))' "$bind_address" \
    || { echo "Bind must be loopback or a private LAN IPv4 address" >&2; exit 2; }
if [[ $action == install && ! -e $state ]]; then install -d -m 0700 "$state"; fi
[[ -d $state && ! -L $state && $(stat -c %a "$state") == 700 ]]
exec 9>"$state/deploy.lock"
flock -n 9

if [[ $action == rollback ]]; then
    owns_board
    docker rm -f "$board"
    exit
fi

verify() {
    owns_board
    [[ $(docker port "$board" 8080/tcp) == "$bind" ]]
    local attempt ready=false
    for attempt in {1..45}; do
        if curl -fsS --max-time 2 "http://$bind/" -o /dev/null 2>/dev/null; then ready=true; break; fi
        sleep 1
    done
    "$ready" || { echo "Host Board did not start at $bind" >&2; return 1; }
    docker exec "$board" grep -Fxq "fateflow.url=$flow_url" "$home/conf/application.properties"
    docker exec "$board" curl -fsS --max-time 5 "$flow_url/v2/site/info/query" \
        | python3 -c 'import json,sys; r=json.load(sys.stdin); sys.exit(not (r.get("code") in (0,"0") and (r.get("data") or {}).get("party_id")))'
    echo "Host Board ready at http://$bind/ via $flow_url"
    [[ ${#task[@]} != 0 ]] || return 0
    docker exec -i "$board" bash -eu -c '
        cd "$1"
        scratch=$(mktemp -d)
        trap '\''rm -rf -- "$scratch"'\'' EXIT
        cat >"$scratch/CheckFateboardDetails.java"
        "$2/javac" -cp "fateboard.jar:lib/*" -d "$scratch" "$scratch/CheckFateboardDetails.java"
        "$2/java" -cp "$scratch:fateboard.jar:lib/*" CheckFateboardDetails "${@:3}"
    ' bash "$home" "$java" "${task[@]}" <"$script_dir/CheckFateboardDetails.java"
}

if [[ $action == verify ]] || docker container inspect "$board" >/dev/null 2>&1; then
    verify
    exit
fi

[[ $(docker inspect -f '{{.State.Running}}:{{if index .NetworkSettings.Networks "'"$network"'"}}attached{{end}}' "$host_flow") == true:attached ]]
image=$(docker inspect -f '{{.Image}}' "$guest")
stage=$(mktemp -d "$state/release.XXXXXXXX")
docker cp "$guest:$home/$jar" "$stage/$jar"
printf '%s  %s\n' "$expected_jar" "$stage/$jar" | sha256sum -c -
chmod 0600 "$stage/$jar"
if [[ ! -f "$state/credentials.properties" ]]; then
    {
        printf 'server.board.login.username=ppci_fate_host\nserver.board.login.password='
        openssl rand -hex 24
    } >"$stage/credentials.properties"
    mv -- "$stage/credentials.properties" "$state/credentials.properties"
fi
[[ $(stat -c %a "$state/credentials.properties") == 600 ]]

cleanup_failed() {
    if owns_board 2>/dev/null; then docker rm -f "$board" >/dev/null; fi
}
trap cleanup_failed EXIT
docker run -d --init --restart unless-stopped --cpus 2 --memory 1g \
    --name "$board" --label "$label=host" --network "$network" -p "$bind:8080" \
    -v "$stage/$jar:$home/$jar:ro" \
    -v "$state/credentials.properties:/run/ppci-fateboard-host.properties:ro" \
    --entrypoint /bin/bash "$image" -eu -c '
        cd "$1"
        umask 077
        {
            sed -E "/^(fateflow\.(url|url-list|http_app_key|http_secret_key)|server\.board\.(login|encrypt)\.[^=]+|server\.servlet\.session\.cookie\.name|zookeeper\.enable)=/d" conf/application.properties
            printf "\nfateflow.url=%s\nzookeeper.enable=false\nserver.board.encrypt.enable=false\nserver.servlet.session.cookie.name=PPCI_FATE_HOST_SESSION\n" "$3"
            cat /run/ppci-fateboard-host.properties
        } >conf/application.properties.host
        mv -- conf/application.properties.host conf/application.properties
        exec "$2/java" -Xms128m -Xmx512m -XX:ActiveProcessorCount=2 \
            -Dspring.config.location="$1/conf/application.properties" -Dssh_config_file="$1/ssh/" \
            -cp "$1/lib/*:$1/fateboard.jar" org.fedai.fate.board.bootstrap.Bootstrap
    ' bash "$home" "$java" "$flow_url" >/dev/null
verify
trap - EXIT
