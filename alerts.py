#!/usr/bin/env python3
"""Command-line entry point for the Price Alert Tool."""
from __future__ import annotations

import argparse
import sys
from alerts_core import InputError, run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Print price alerts from CSV prices and JSON rules.")
    parser.add_argument("prices_csv", help="CSV with date,instrument,close columns")
    parser.add_argument("rules_json", help="JSON list of alert rules")
    args = parser.parse_args(argv)
    try:
        alerts = run(args.prices_csv, args.rules_json, lambda message: print(message, file=sys.stderr))
    except InputError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    for alert in alerts:
        print(alert.line())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
