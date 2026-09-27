"""把 FastAPI 的 OpenAPI schema 写到 backend/openapi.json。

api-client 的类型由该文件生成，改动接口后执行：make openapi && pnpm run api-client:generate
"""

from __future__ import annotations

import json
import pathlib
import sys

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))


def main() -> int:
    from app.main import app

    out = BACKEND_ROOT / "openapi.json"
    payload = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True)
    out.write_text(payload + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
