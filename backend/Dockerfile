FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# 是否把 ml 额外依赖（sentence-transformers + torch，约 1GB）打进镜像。
# 默认 0：CI 与本地开发用 hash 向量，镜像小、构建快。
# 生产要真正的语义搜索/聚类时用 --build-arg WITH_ML=1 构建（见 docs/adr/0012）。
ARG WITH_ML=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN if [ "$WITH_ML" = "1" ]; then uv sync --frozen --no-install-project --no-dev --extra ml; \
    else uv sync --frozen --no-install-project --no-dev; fi

# 模型权重在构建期下载好：容器运行时不该依赖 HuggingFace 可达（版本也没法审计）。
# 写成一个脚本文件比塞在 RUN 里更易读。
ARG EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
ENV HF_HOME=/app/.cache/huggingface \
    EMBEDDING_MODEL=${EMBEDDING_MODEL}
COPY docker/prefetch_model.py /tmp/prefetch_model.py
RUN if [ "$WITH_ML" = "1" ]; then \
      python /tmp/prefetch_model.py || echo 'WARN: 模型预下载失败，运行时首次调用会再试'; \
    fi

COPY app ./app
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY scripts ./scripts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
