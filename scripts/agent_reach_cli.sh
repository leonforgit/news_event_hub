#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
AGENT_REACH_HOME="${AGENT_REACH_HOME:-${ROOT_DIR}/runtime/agent_reach}"
AGENT_REACH_BIN="${AGENT_REACH_BIN:-${AGENT_REACH_HOME}/.venv/bin/agent-reach}"
export PATH="${AGENT_REACH_HOME}/.venv/bin:${PATH}"

if [[ ! -x "${AGENT_REACH_BIN}" ]]; then
  echo "agent-reach is not installed at ${AGENT_REACH_BIN}" >&2
  echo "Run: ${SCRIPT_DIR}/install_agent_reach.sh" >&2
  exit 1
fi

exec "${AGENT_REACH_BIN}" "$@"
