#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_PORT="${BACKEND_PORT:-18080}"
FRONTEND_PORT="${FRONTEND_PORT:-15173}"
CAREER_OS_SUFFIX="${1:-${CAREER_OS_SUFFIX:-}}"

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

validate_suffix() {
  if [[ ! "${1}" =~ ^[a-zA-Z0-9_-]+$ ]]; then
    echo "错误: 后缀「${1}」非法，仅允许字母、数字、_、-" >&2
    exit 1
  fi
}

if [[ -z "${CAREER_OS_SUFFIX}" ]]; then
  echo "用法: make dev <suffix>   或   ./scripts/dev.sh <suffix>" >&2
  echo "示例: make dev blank" >&2
  exit 1
fi

prepare_data_dirs() {
  mkdir -p "${ROOT}/backend/data/${CAREER_OS_SUFFIX}" \
    "${ROOT}/backend/output/${CAREER_OS_SUFFIX}" \
    "${ROOT}/backend/data/${CAREER_OS_SUFFIX}/market_research/runtime"
}

require_cmd uv
require_cmd npm

CLEANED=0
cleanup() {
  if [[ "${CLEANED}" -eq 1 ]]; then
    return
  fi
  CLEANED=1
  local pids
  pids="$(jobs -p 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    kill ${pids} 2>/dev/null || true
    wait ${pids} 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

validate_suffix "${CAREER_OS_SUFFIX}"

export DATA_DIR="./data/${CAREER_OS_SUFFIX}"
export OUTPUT_DIR="./output/${CAREER_OS_SUFFIX}"

load_dotenv "${ROOT}/backend/.env"
prepare_data_dirs

echo ">>> 初始化空档案结构（无预填业务数据）..."
(
  cd "${ROOT}/backend"
  export DATA_DIR OUTPUT_DIR
  uv run python -c "from career_os.platform.store.profile import ProfileStore; ProfileStore().ensure_empty_profile()"
)

echo ">>> 环境 ${CAREER_OS_SUFFIX}  DATA_DIR=${DATA_DIR}  OUTPUT_DIR=${OUTPUT_DIR}"

echo ">>> 同步后端依赖..."
(cd "${ROOT}/backend" && uv sync)

RUNTIME_DIR="${ROOT}/backend/data/${CAREER_OS_SUFFIX}/market_research/runtime"
PROCESS_REGISTRY="${ROOT}/scripts/process_registry.py"
(
  cd "${ROOT}/backend"
  uv run python "${PROCESS_REGISTRY}" record "${RUNTIME_DIR}" dev-shell "$$" "${CAREER_OS_SUFFIX}" "scripts/dev.sh"
)

echo ">>> 启动后端 http://127.0.0.1:${BACKEND_PORT}"
(
  cd "${ROOT}/backend"
  export DATA_DIR OUTPUT_DIR
  exec uv run uvicorn career_os.main:app --reload --port "${BACKEND_PORT}"
) &
BACKEND_PID=$!
(
  cd "${ROOT}/backend"
  uv run python "${PROCESS_REGISTRY}" record "${RUNTIME_DIR}" backend "${BACKEND_PID}" "${CAREER_OS_SUFFIX}" "uvicorn"
)

if [[ ! -d "${ROOT}/web/node_modules" ]]; then
  echo ">>> 安装前端依赖..."
  (cd "${ROOT}/web" && npm install)
fi

echo ">>> 启动前端 http://localhost:${FRONTEND_PORT}"
(
  cd "${ROOT}/web"
  exec npm run dev -- --port "${FRONTEND_PORT}"
) &
FRONTEND_PID=$!
(
  cd "${ROOT}/backend"
  uv run python "${PROCESS_REGISTRY}" record "${RUNTIME_DIR}" frontend "${FRONTEND_PID}" "${CAREER_OS_SUFFIX}" "npm"
)

wait "${FRONTEND_PID}"
