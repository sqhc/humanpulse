"""本地句向量（sentence-transformers）：生产环境使用，需安装 ml 额外依赖。"""

from __future__ import annotations

import importlib
from typing import Any

from app.config import get_settings
from app.embedding.base import l2_normalize


class LocalEmbedder:
    """用 sentence-transformers 生成多语种句向量。

    模型体积较大，因此只在实例化时才导入该可选依赖；
    未安装时抛 RuntimeError 并提示安装命令，而不是让整个进程在导入期崩溃。
    """

    name: str
    dim: int

    def __init__(self, model_name: str | None = None) -> None:
        try:
            # 用 importlib 而不是顶层 import：sentence-transformers 是可选依赖，
            # 且没有类型存根，string 形式的惰性导入可避免 mypy 对缺失模块报错。
            module = importlib.import_module("sentence_transformers")
        except ImportError as exc:
            raise RuntimeError(
                "未安装 sentence-transformers，无法使用 local 向量化；请先执行：uv sync --extra ml"
            ) from exc
        resolved = model_name or get_settings().embedding_model
        factory: Any = module.SentenceTransformer
        self._model: Any = factory(resolved)
        self.name = f"local-{resolved}"
        # sentence-transformers 6.x 把 get_sentence_embedding_dimension 改名为
        # get_embedding_dimension；两个名字都试，避免被弃用警告刷屏。
        get_dim: Any = getattr(self._model, "get_embedding_dimension", None) or getattr(
            self._model, "get_sentence_embedding_dimension", None
        )
        if get_dim is None:
            raise RuntimeError(f"无法从模型 {resolved} 获取向量维度")
        raw_dim = get_dim()
        if raw_dim is None:
            raise RuntimeError(f"无法从模型 {resolved} 获取向量维度")
        self.dim = int(raw_dim)

    def embed(self, text: str) -> list[float]:
        vector = self._model.encode(text)
        return l2_normalize([float(value) for value in vector])
