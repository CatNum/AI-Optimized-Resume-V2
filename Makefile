.PHONY: dev dev-demo dev-test install

# 非 login shell 下补全 uv / Homebrew 常见路径
export PATH := $(HOME)/.local/bin:$(HOME)/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$(PATH)

dev: dev-demo

dev-demo:
	@CAREER_OS_ENV_FILE=.env.demo ./scripts/dev.sh

dev-test:
	@CAREER_OS_ENV_FILE=.env.test ./scripts/dev.sh

install:
	cd backend && uv sync
	cd web && npm install
	@test -f backend/.env || cp backend/.env.example backend/.env
