#!/usr/bin/env bash
set -euo pipefail
SOURCE="${PPCI_SOURCE_ROOT:-/opt/ppci-source}"
BUILD="${PPCI_BUILD_ROOT:-/opt/ppci-build}"
export GOMAXPROCS=2 GOMEMLIMIT=1500MiB CGO_ENABLED=0
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
export GOMODCACHE="$BUILD/gomod" GOCACHE="$BUILD/gocache"
case "${1:-}" in
  paddle)
    mkdir -p "$BUILD/paddle"
    cd "$SOURCE/PaddleDTX/dai"
    go build -p 2 -ldflags='-s -w' -o "$BUILD/paddle/paddlempc" ./blockchain/xchain/contract
    go build -p 2 -ldflags='-s -w' -o "$BUILD/paddle/requester-cli-current" ./requester/cmd
    exit 0
    ;;
  kuscia)
    CONTEXT="$BUILD/kuscia-image"
    mkdir -p "$CONTEXT"
    cd "$SOURCE/NewProject/kuscia"
    go build -p 2 -ldflags='-s -w' -o "$CONTEXT/kuscia" ./cmd/kuscia
    rsync -a scripts crds "$CONTEXT/"
    cat > "$CONTEXT/Dockerfile" <<'EOF'
FROM secretflow-registry.cn-hangzhou.cr.aliyuncs.com/secretflow/kuscia:1.2.0b0
COPY kuscia /home/kuscia/bin/kuscia
COPY scripts /home/kuscia/scripts
COPY crds /home/kuscia/crds
EOF
    IMAGE=ppci/kuscia:home-20260912
    ;;
  adapter)
    CONTEXT="$BUILD/fate-adapter"
    mkdir -p "$CONTEXT"
    cd "$SOURCE/NewProject/thirdparty/fate2-adapter"
    go test -p 2 ./...
    go build -p 2 -ldflags='-s -w' -o "$CONTEXT/adapter" ./cmd/adapter
    mkdir -p "$CONTEXT/certs"
    CA_BUNDLE="${PPCI_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
    [[ -f "$CA_BUNDLE" ]] || CA_BUNDLE=/etc/pki/tls/certs/ca-bundle.crt
    cp "$CA_BUNDLE" "$CONTEXT/certs/ca-certificates.crt"
    cat > "$CONTEXT/Dockerfile" <<'EOF'
FROM scratch
WORKDIR /app
COPY adapter /app/fate2-adapter
COPY certs /etc/ssl/certs
ENTRYPOINT ["/app/fate2-adapter"]
EOF
    IMAGE=secretflow/fate2-adapter:0.2.0-native
    ;;
  *) echo 'Usage: build-runtime.sh kuscia|adapter|paddle' >&2; exit 2 ;;
esac
# Anolis packages Docker without buildx; its built-in legacy builder uses local bases.
if ! docker buildx version >/dev/null 2>&1; then export DOCKER_BUILDKIT=0; fi
docker build -t "$IMAGE" "$CONTEXT"
