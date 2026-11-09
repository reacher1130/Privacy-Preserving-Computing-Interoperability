#!/bin/sh
set -eu
# Keep the engine's glibc private; Python continues using its tested system libraries.
exec /opt/bfia/engine/lib/ld-linux-x86-64.so.2 \
  --library-path /opt/bfia/engine/lib /opt/bfia/engine/ic_main "$@"
