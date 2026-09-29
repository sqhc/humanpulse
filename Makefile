.DEFAULT_GOAL := help
SHELL := /bin/bash

BACKEND := backend

# 受限文件沙箱下，uv 与 buildx 的默认缓存目录（~/.cache/uv、~/.docker/buildx）不可写，
# 统一重定向到仓库内 .cache/（已 gitignore）。需要时可覆盖：UV_CACHE_DIR=/x make verify
CACHE_ROOT := $(CURDIR)/.cache
UV_CACHE_DIR ?= $(CACHE_ROOT)/uv
BUILDX_CONFIG ?= $(CACHE_ROOT)/buildx
# 模型权重同样默认落在 ~/.cache，受限沙箱下会被拒绝，一并重定向
HF_HOME ?= $(CACHE_ROOT)/huggingface
TORCH_HOME ?= $(CACHE_ROOT)/torch
export UV_CACHE_DIR BUILDX_CONFIG HF_HOME TORCH_HOME

.PHONY: help doctor bootstrap install ml lint typecheck test build verify openapi \
        migrate seed demo reembed brief entities reprice dev dev-web logs dev-down smoke collect-once prod-config deploy \
        restore-drill clean

help: ## 显示所有可用命令
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

doctor: ## 检查本机依赖、.env 与端口占用
	@bash scripts/doctor.sh

install: ## 安装前后端依赖
	cd $(BACKEND) && uv sync
	pnpm install

ml: ## 安装本地语义向量依赖（sentence-transformers，体积较大）
	cd $(BACKEND) && uv sync --extra ml

bootstrap: install ## 安装依赖并准备 .env
	@test -f .env || (cp .env.example .env && echo "已生成 .env，请填入 DEEPSEEK_API_KEY / ADMIN_API_KEY")

lint: ## 后端 ruff + 前端 eslint
	cd $(BACKEND) && uv run ruff check . && uv run ruff format --check .
	pnpm run lint

typecheck: ## 后端 mypy + 前端 tsc
	cd $(BACKEND) && uv run mypy app
	pnpm run typecheck

test: ## 后端 pytest + 前端 vitest
	cd $(BACKEND) && uv run pytest -q
	pnpm run test

build: ## 前端生产构建 + api-client 类型检查
	pnpm run build
	pnpm run api-client:typecheck

openapi: ## 导出后端 OpenAPI 到 backend/openapi.json
	cd $(BACKEND) && uv run python scripts/export_openapi.py

.env:
	@cp .env.example .env
	@echo "已从 .env.example 生成 .env（部署前请填入真实密钥）"

compose-config: .env ## 校验 compose 文件语法
	@docker compose -f docker-compose.yml config -q && echo "docker-compose.yml OK"
	@docker compose -f docker-compose.prod.yml config -q && echo "docker-compose.prod.yml OK"

verify: lint typecheck test build compose-config ## 上传前必须全绿
	@echo "verify 全部通过"

migrate: ## 执行数据库迁移（alembic upgrade head）
	cd $(BACKEND) && uv run python -m app.cli migrate

seed: ## 导入 infra/seed/sources.yaml 中的源
	cd $(BACKEND) && uv run python -m app.cli seed --file ../infra/seed/sources.yaml --prune

demo: ## 用合成数据跑通采集→处理→聚类（不联网、不花钱）
	cd $(BACKEND) && uv run python -m app.cli demo

brief: ## 生成简报（KIND=daily|weekly；FORCE=1 强制重跑）
	cd $(BACKEND) && uv run python -m app.cli brief --kind $(or $(KIND),daily) $(if $(FORCE),--force,)

entities: ## 把历史 analyses.entities 回填进实体表（幂等）
	cd $(BACKEND) && uv run python -m app.cli backfill-entities

reprice: ## 按官方定价重算历史成本（输入按未命中计）
	cd $(BACKEND) && uv run python -m app.cli reprice

reembed: ## 用当前向量模型重新嵌入并重建聚类（需 uv sync --extra ml）
	cd $(BACKEND) && uv run python -m app.cli reembed

dev: ## 启动本地依赖服务（db + api + worker）
	docker compose up -d --wait db api worker

dev-web: ## 启动前端开发服务器
	pnpm run dev:web

logs: ## 跟踪 compose 日志
	docker compose logs -f --tail=100

dev-down: ## 停止本地服务
	docker compose down

smoke: ## 起栈 → 探活 → 收栈
	@bash scripts/smoke.sh

collect-once: ## 手动触发一次采集（需栈已起，且在环境中导出 ADMIN_API_KEY）
	curl -fsS -X POST -H "X-API-Key: ${ADMIN_API_KEY:?请先导出 ADMIN_API_KEY}" \
		"http://localhost:${API_PORT:-8000}/api/v1/admin/jobs/collect/run?force=true"
	@echo

prod-config: ## 渲染生产 compose（需 .env 中的 DOMAIN/TAG）
	docker compose -f docker-compose.prod.yml config

deploy: ## 在 VPS 上执行（详见 docs/runbook.md）
	@bash scripts/deploy.sh

restore-drill: ## 备份恢复演练（详见 docs/runbook.md）
	@bash scripts/restore-drill.sh

clean: ## 清理构建产物与缓存
	rm -rf web/dist packages/*/dist .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
