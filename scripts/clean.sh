#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAREER_OS_SUFFIX="${1:-${CAREER_OS_SUFFIX:-}}"
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

validate_suffix() {
  if [[ ! "${1}" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "错误: 后缀「${1}」非法，仅允许字母、数字、_、-" >&2
    exit 1
  fi
}

if [[ -z "${CAREER_OS_SUFFIX}" ]]; then
  echo "用法: make clean <suffix>   或   ./scripts/clean.sh <suffix>" >&2
  echo "示例: make clean demo" >&2
  exit 1
fi

validate_suffix "${CAREER_OS_SUFFIX}"

DATA_DIR="${ROOT}/backend/data/${CAREER_OS_SUFFIX}"
OUTPUT_DIR="${ROOT}/backend/output/${CAREER_OS_SUFFIX}"
RUNTIME_DIR="${DATA_DIR}/market_research/runtime"

if [[ ! -d "${DATA_DIR}" && ! -d "${OUTPUT_DIR}" ]]; then
  echo ">>> 环境「${CAREER_OS_SUFFIX}」无数据，无需清除"
  exit 0
fi

if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
  "${ROOT}/backend/.venv/bin/python" "${ROOT}/scripts/process_registry.py" cleanup "${RUNTIME_DIR}" "${CAREER_OS_SUFFIX}" "${DATA_DIR}"
elif command -v uv >/dev/null 2>&1; then
  (cd "${ROOT}/backend" && uv run python "${ROOT}/scripts/process_registry.py" cleanup "${RUNTIME_DIR}" "${CAREER_OS_SUFFIX}" "${DATA_DIR}")
else
  echo "错误: 无法加载安全进程清理器；请先安装 uv 或保留 backend/.venv。" >&2
  exit 127
fi

rm -rf "${DATA_DIR}" "${OUTPUT_DIR}"
echo ">>> 已清除环境「${CAREER_OS_SUFFIX}」"
echo "    ${DATA_DIR}"
echo "    ${OUTPUT_DIR}"
echo ">>> 重新启动: make dev ${CAREER_OS_SUFFIX}"
echo ">>> 浏览器建议清 session: localStorage.removeItem('session_id')"
