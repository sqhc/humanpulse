# humanpulse backend

FastAPI 服务：`/api/v1` REST 接口、采集器、AI 处理流水线与定时简报。

```bash
uv sync                 # 安装依赖
uv run uvicorn app.main:app --reload
uv run pytest           # 测试
uv run alembic upgrade head
```

Phase 0 仅提供健康检查与配置骨架；采集/处理模块在 Phase 1 落地（见 ../docs/adr/）。
