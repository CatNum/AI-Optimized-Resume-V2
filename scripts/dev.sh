#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-18080}"
FRONTEND_PORT="${FRONTEND_PORT:-15173}"
ENV_PROFILE="${1:-${CAREER_OS_ENV_FILE:-.env.demo}}"

# make / 非 login shell 常不含 ~/.local/bin（uv 默认安装路径）
export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:${PATH}"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "错误: 未找到命令「$1」。" >&2
    case "$1" in
      uv)
        echo "安装: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
        echo "或确保 ~/.local/bin 已加入 PATH。" >&2
        ;;
      npm)
        echo "请先安装 Node.js: https://nodejs.org/" >&2
        ;;
    esac
    exit 127
  fi
}

load_dotenv() {
  local file="$1"
  if [[ -f "${file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${file}"
    set +a
  fi
}

require_cmd uv
require_cmd npm

cleanup() {
  local pids
  pids="$(jobs -p 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill ${pids} 2>/dev/null || true
    wait ${pids} 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# LLM 等共用配置 + 环境专用 DATA_DIR / OUTPUT_DIR
load_dotenv "${ROOT}/backend/.env"
load_dotenv "${ROOT}/backend/${ENV_PROFILE}"

echo ">>> 环境配置 ${ENV_PROFILE}"
echo ">>> DATA_DIR=${DATA_DIR:-./data}  OUTPUT_DIR=${OUTPUT_DIR:-./output}"

echo ">>> 同步后端依赖..."
(cd "${ROOT}/backend" && uv sync)

echo ">>> 启动后端 http://127.0.0.1:${BACKEND_PORT}"
(
  cd "${ROOT}/backend"
  export DATA_DIR="${DATA_DIR:-./data}"
  export OUTPUT_DIR="${OUTPUT_DIR:-./output}"
  uv run uvicorn career_os.main:app --reload --port "${BACKEND_PORT}"
) &

if [[ ! -d "${ROOT}/web/node_modules" ]]; then
  echo ">>> 安装前端依赖..."
  (cd "${ROOT}/web" && npm install)
fi

echo ">>> 启动前端 http://localhost:${FRONTEND_PORT}"
(cd "${ROOT}/web" && npm run dev -- --port "${FRONTEND_PORT}")
