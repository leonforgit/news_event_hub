#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
RUNTIME_HOME="${BROWSER_SIGNAL_HOME:-${ROOT_DIR}/runtime/browser_signal}"
VENV_DIR="${RUNTIME_HOME}/.venv"

mkdir -p "${RUNTIME_HOME}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install -r "${ROOT_DIR}/requirements.txt"
"${VENV_DIR}/bin/python" -m pip install "playwright==1.59.0"
"${VENV_DIR}/bin/python" -m playwright install chromium

echo "browser_signal_home=${RUNTIME_HOME}"
echo "browser_signal_python=${VENV_DIR}/bin/python"
