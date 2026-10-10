"""构建期预下载向量模型权重。

运行时（尤其生产）不应依赖 HuggingFace 可达：一是网络/限流会让首个搜索请求失败，
二是模型权重是事实上的依赖，应该在镜像里固定下来。
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    model = os.environ.get("EMBEDDING_MODEL", "paraphrase-multilingual-MiniLM-L12-v2")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        print("未安装 sentence-transformers，跳过预下载")
        return 1
    print(f"预下载向量模型：{model}")
    SentenceTransformer(model)
    print("完成")
    return 0


if __name__ == "__main__":
    sys.exit(main())
