"""serve.py — run the Circuit Circus site.

    uv run ccircus                 # serve on http://127.0.0.1:8000
    uv run uvicorn web.app:app --reload   # dev server with autoreload
"""

from __future__ import annotations

import os


def main() -> None:
    import uvicorn

    host = os.environ.get("CCIRCUS_HOST", "127.0.0.1")
    port = int(os.environ.get("CCIRCUS_PORT", "8000"))
    uvicorn.run("web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
