#!/usr/bin/env python3
"""Read-only lake inventory. Does not download a corpus or stop services."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atlas.data.inventory import inspect_source, write_access_failure, write_environment


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        print(f"Refusing to overwrite existing run: {args.output}", file=sys.stderr)
        return 2
    try:
        result = inspect_source(args.root, args.output)
    except (FileNotFoundError, NotADirectoryError, PermissionError) as exc:
        if args.output.exists():
            print(f"Refusing to overwrite existing run: {args.output}", file=sys.stderr)
            return 2
        write_access_failure(args.output, exc)
        _record_environment(args.output)
        print("blocked")
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    _record_environment(args.output)
    print(result["status"])
    return 0 if result["status"] == "completed" else 2


def _record_environment(output: Path) -> None:
    try:
        write_environment(output)
    except OSError as exc:
        print(f"environment record failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
