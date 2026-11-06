#!/usr/bin/env bash
# Run the linux/amd64 PaddleDTX requester through the local executor container.
# SecretPad passes a host-side config path; the container copy is authoritative.
set -eu

args=()
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-c" ] && [ "$#" -ge 2 ]; then
    shift
    shift
    continue
  fi
  args+=("$1")
  shift
done

requester_binary="${PADDLEDTX_REQUESTER_BINARY:-/home/requester-cli-current}"
demo_skip_health="${PADDLEDTX_DEMO_SKIP_HEALTH:-false}"

exec docker exec -e "PADDLEDTX_DEMO_SKIP_HEALTH=${demo_skip_health}" -w /home executor1.node.com "${requester_binary}" \
  -c /home/conf/requester-config.toml "${args[@]}"
