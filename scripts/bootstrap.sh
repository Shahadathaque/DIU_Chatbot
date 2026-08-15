#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3.11}"
VENV_DIR="${VENV_DIR:-${PROJECT_ROOT}/.venv}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  printf 'Python 3.11 is required. Set PYTHON_BIN to a compatible Python executable.\n' >&2
  exit 2
fi

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/python" -m pip install --upgrade pip
"${VENV_DIR}/bin/python" -m pip install -r "${PROJECT_ROOT}/requirements.txt"

if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
  cp "${PROJECT_ROOT}/.env.example" "${PROJECT_ROOT}/.env"
fi

exec "${VENV_DIR}/bin/python" "${PROJECT_ROOT}/scripts/artifacts.py"
