.PHONY: dev clean install

# 非 login shell 下补全 uv / Homebrew 常见路径
export PATH := $(HOME)/.local/bin:$(HOME)/.cargo/bin:/opt/homebrew/bin:/usr/local/bin:$(PATH)

# make dev <suffix> / make clean <suffix>
ifneq ($(filter dev clean,$(MAKECMDGOALS)),)
$(filter-out dev clean,$(MAKECMDGOALS)):
	@:
endif

dev:
	@suffix="$(word 2,$(MAKECMDGOALS))"; \
	if [ -z "$$suffix" ]; then \
	  echo "用法: make dev <suffix>"; \
	  echo "示例: make dev blank   make dev test   make dev demo"; \
	  exit 1; \
	fi; \
	CAREER_OS_SUFFIX="$$suffix" ./scripts/dev.sh

clean:
	@suffix="$(word 2,$(MAKECMDGOALS))"; \
	if [ -z "$$suffix" ]; then \
	  echo "用法: make clean <suffix>"; \
	  echo "示例: make clean demo   make clean test"; \
	  exit 1; \
	fi; \
	./scripts/clean.sh "$$suffix"

install:
	cd backend && uv sync
	cd web && npm install
	@test -f backend/.env || cp backend/.env.example backend/.env
