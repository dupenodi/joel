#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HYDRA_REPO="${HYDRA_REPO:-"$ROOT/../hydradb"}"
DATASET="${JOEL_DATASET:-main}"
STORE_ROOT="$ROOT/.hydradb/$DATASET"

mkdir -p "$STORE_ROOT/store" "$STORE_ROOT/cache"
printf '%s\n' "${HYDRA_TOKEN:-local-development-token-32-bytes}" \
  > "$STORE_ROOT/auth-token"

export CLOUD_PROVIDER=local
export LOCAL_PATH="$STORE_ROOT/store"
export GRAPH_NAMESPACE="${HYDRA_NAMESPACE:-default}"
export GRAPH_ID=default
export GRAPH_CELL_ID="${HYDRA_CELL:-cell-0}"
export GRAPH_CELLS="${HYDRA_CELL:-cell-0}"
export GRAPH_DATA_PATH=data
export GRAPH_ALLOW_PLAINTEXT=true
export GRAPH_AUTH_TOKEN_FILE="$STORE_ROOT/auth-token"
export GRAPH_DATA_CACHE_BYTES=67108864
export GRAPH_DATA_CACHE_DIR="$STORE_ROOT/cache"
export GRAPH_NODE_ID=node-0
export GRAPH_BOLT_ADDR=127.0.0.1:7687
export GRAPH_ADVERTISED_BOLT_ADDR=127.0.0.1:7687
export GRAPH_BOLT_NODE_ADDRESSES=node-0=127.0.0.1:7687
export GRAPH_HTTP_ADDR=127.0.0.1:8443
export GRAPH_ADMIN_ADDR=127.0.0.1:9090
export RUST_MIN_STACK=33554432

if command -v brew >/dev/null; then
  export BINDGEN_EXTRA_CLANG_ARGS="-I$(brew --prefix)/include"
  export LIBRARY_PATH="$(brew --prefix)/lib"
fi

cd "$HYDRA_REPO"
exec cargo run --locked --features server-runtime --bin graph-node
