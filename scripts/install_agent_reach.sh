#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

AGENT_REACH_HOME="${AGENT_REACH_HOME:-${ROOT_DIR}/runtime/agent_reach}"
VENV_DIR="${AGENT_REACH_HOME}/.venv"
REPO_SPEC="${AGENT_REACH_REPO_SPEC:-git+https://github.com/Panniantong/Agent-Reach.git}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "missing required command: $1" >&2
    exit 1
  fi
}

require_cmd "${PYTHON_BIN}"

venv_is_healthy() {
  [[ -x "${VENV_DIR}/bin/python" ]] || return 1
  "${VENV_DIR}/bin/python" -c "import sys; print(sys.executable)" >/dev/null 2>&1 || return 1
  return 0
}

ensure_pip() {
  if ! "${VENV_DIR}/bin/python" -m pip --version >/dev/null 2>&1; then
    "${VENV_DIR}/bin/python" -m ensurepip --upgrade
  fi
}

configure_yt_dlp() {
  if command -v node >/dev/null 2>&1; then
    local config_dir="${HOME}/.config/yt-dlp"
    local config_file="${config_dir}/config"
    mkdir -p "${config_dir}"
    grep -qxF -- "--js-runtimes node" "${config_file}" 2>/dev/null || printf '%s\n' "--js-runtimes node" >> "${config_file}"
  fi
}

install_wrapper() {
  cat > "${VENV_DIR}/bin/agent-reach" <<EOF
#!/usr/bin/env bash
exec "${VENV_DIR}/bin/python" -m agent_reach.cli "\$@"
EOF
  chmod +x "${VENV_DIR}/bin/agent-reach"
}

mkdir -p "${AGENT_REACH_HOME}" \
         "${ROOT_DIR}/state/auth/agent_reach" \
         "${ROOT_DIR}/state/agent_reach" \
         "${ROOT_DIR}/logs"

if ! venv_is_healthy; then
  rm -rf "${VENV_DIR}"
  if command -v uv >/dev/null 2>&1; then
    uv venv "${VENV_DIR}" --python "${PYTHON_BIN}"
  else
    "${PYTHON_BIN}" -m venv "${VENV_DIR}"
  fi
fi

ensure_pip

"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
"${VENV_DIR}/bin/python" -m pip install --upgrade "${REPO_SPEC}"
install_wrapper
configure_yt_dlp

echo "agent_reach_home=${AGENT_REACH_HOME}"
echo "agent_reach_bin=${VENV_DIR}/bin/agent-reach"
"${VENV_DIR}/bin/agent-reach" --version
