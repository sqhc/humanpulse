"""ORM 基类。Phase 1 在此登记 sources / documents / analyses 等表。"""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
