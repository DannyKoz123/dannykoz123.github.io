#!/bin/bash
# Install the trade-gap-monitor Python environment in cloud sessions.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR/projects/trade-gap-monitor"
uv sync
