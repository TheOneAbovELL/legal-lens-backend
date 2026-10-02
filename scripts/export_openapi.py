"""Export the OpenAPI document to frontend/contract/openapi.json (no server, no lifespan).

The frontend contract test (frontend/tests/contract.test.ts) checks every path the client calls
and every response field it reads against this file, so backend and frontend cannot drift
silently. Run it after changing any schema or router:

    python scripts/export_openapi.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "frontend" / "contract" / "openapi.json"


def main() -> int:
    from app.core.config import Settings
    from app.main import create_app

    # Test environment: no secrets are needed to build the app object (nothing is served).
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None, app_env="test", log_json=False, log_level="WARNING", diagnostics_enabled=True, docs_enabled=True,
    )
    spec = create_app(settings).openapi()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    changed = not OUT.exists() or OUT.read_text(encoding="utf-8") != text
    OUT.write_text(text, encoding="utf-8")
    print(f"{'updated' if changed else 'unchanged'}: {OUT.relative_to(ROOT)} ({len(spec['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
