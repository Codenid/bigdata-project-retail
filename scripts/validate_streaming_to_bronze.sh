#!/usr/bin/env bash
set -euo pipefail
RETAILSMART_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RETAILSMART_ROOT"
exec python3 -m pipelines.streaming.manage --mode validate "$@"
