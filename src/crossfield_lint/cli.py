"""Command-line entry point.

Exit codes:
    0 -- clean, no findings
    1 -- findings reported
    2 -- could not analyse (bad path, unparseable file)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from crossfield_lint.static import check_paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crossfield-lint",
        description=(
            "Find pydantic v2 field validators that read info.data for a "
            "field that has not been validated yet."
        ),
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to check.")
    parser.add_argument(
        "--format", choices=["text", "json"], default="text", help="Output format (default: text)."
    )
    args = parser.parse_args(argv)

    missing = [p for p in args.paths if not Path(p).exists()]
    if missing:
        for p in missing:
            print(f"crossfield-lint: no such file or directory: {p}", file=sys.stderr)
        return 2

    result = check_paths(args.paths)

    if args.format == "json":
        payload = {
            "models_checked": result.models_checked,
            "findings": [f.as_dict() for f in result.findings],
            "errors": [{"file": f, "message": m} for f, m in result.files_with_errors],
        }
        print(json.dumps(payload, indent=2))
    else:
        for finding in result.findings:
            print(finding.format_text())
        if result.files_with_errors:
            for f, m in result.files_with_errors:
                print(f"crossfield-lint: could not parse {f}: {m}", file=sys.stderr)
        summary = f"{len(result.findings)} finding(s) in {result.models_checked} model(s) checked"
        print(summary, file=sys.stderr)

    if result.files_with_errors:
        return 2
    if result.findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
