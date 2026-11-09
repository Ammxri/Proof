"""Write the JSON Schemas in ``schema/`` from the Pydantic models (PR-F01).

The schema files are generated, never edited by hand. A test compares the committed files with a fresh export.

Usage:
    uv run python tools/export_schemas.py            # write schema/*.schema.json
    uv run python tools/export_schemas.py --check    # exit 1 if a schema file is out of date
"""

from __future__ import annotations

import sys
from pathlib import Path

from proof.cases.model import case_json_schema, schema_text

OUTPUT = Path(__file__).resolve().parent.parent / "schema"


def render() -> dict[str, str]:
    """File name → text of every schema."""
    return {"case.schema.json": schema_text(case_json_schema())}


def main(argv: list[str]) -> int:
    if argv not in ([], ["--check"]):
        print(__doc__, file=sys.stderr)
        return 2
    files = render()
    if argv == ["--check"]:
        stale = []
        for name, text in files.items():
            path = OUTPUT / name
            if not path.is_file() or path.read_bytes().decode("utf-8") != text:
                stale.append(path)
        for path in stale:
            print(f"{path} is out of date; run: uv run python tools/export_schemas.py", file=sys.stderr)
        return 1 if stale else 0
    OUTPUT.mkdir(exist_ok=True)
    for name, text in files.items():
        path = OUTPUT / name
        path.write_bytes(text.encode("utf-8"))
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
