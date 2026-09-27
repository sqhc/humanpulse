"""数据库引擎、会话工厂与健康探测。

支持按 URL 缓存引擎：运行期用 settings.database_url，测试可显式传 TEST_DATABASE_URL。
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engines: dict[str, AsyncEngine] = {}
_sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}


def get_engine(url: str | None = None) -> AsyncEngine:
    resolved = url or get_settings().database_url
    engine = _engines.get(resolved)
    if engine is None:
        engine = create_async_engine(resolved, pool_pre_ping=True)
        _engines[resolved] = engine
    return engine


def get_sessionmaker(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    resolved = url or get_settings().database_url
    maker = _sessionmakers.get(resolved)
    if maker is None:
        maker = async_sessionmaker(get_engine(resolved), expire_on_commit=False, autoflush=False)
        _sessionmakers[resolved] = maker
    return maker


@asynccontextmanager
async def session_scope(url: str | None = None) -> AsyncIterator[AsyncSession]:
    """提交或回滚都自动收尾的会话上下文；脚本与后台任务用它。"""
    async with get_sessionmaker(url)() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每个请求一个会话。"""
    async with session_scope() as session:
        yield session


async def ping(url: str | None = None) -> bool:
    """能在 2 秒内跑通 SELECT 1 视为可用。"""
    try:
        async with get_engine(url).connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        # 探测失败即视为不可用，不向上抛（/ready 用 503 表达）
        return False


async def dispose() -> None:
    for engine in list(_engines.values()):
        await engine.dispose()
    _engines.clear()
    _sessionmakers.clear()
