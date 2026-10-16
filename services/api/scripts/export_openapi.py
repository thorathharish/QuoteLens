"""Write the API's OpenAPI document (source of truth for frontend types, ADR-0007).

uv run python scripts/export_openapi.py ../../apps/web/lib/api/openapi.json
"""

import json
import sys
from pathlib import Path

from app.config import Settings
from app.container import build_container
from app.infra.repositories.memory import InMemoryDocumentStore
from app.main_api import create_app


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    settings = Settings(env="test", llm_enabled=False, _env_file=None)
    app = create_app(build_container(settings, store=InMemoryDocumentStore()))
    target.write_text(json.dumps(app.openapi(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
