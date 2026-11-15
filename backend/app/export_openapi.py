"""Write the app's OpenAPI document, the input for the web app's generated types.

uv run python -m app.export_openapi ../frontend/src/api/openapi.json
"""

import json
import sys
from pathlib import Path

from app.main import create_app


def render() -> str:
    return json.dumps(create_app().openapi(), indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    Path(sys.argv[1]).write_bytes(render().encode("utf-8"))
