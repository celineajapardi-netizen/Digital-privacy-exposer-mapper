"""
Run an analysis from the terminal.

    python -m shadow.cli school city schedule
    python -m shadow.cli --list          # show every kind of information
    python -m shadow.cli --json username school schedule
"""

from __future__ import annotations

import argparse
import json
import sys

from .catalogue import CATALOGUE, CATALOGUE_BY_KEY
from .engine import analyse
from .rules import SEVERITY_LABEL


def print_catalogue() -> None:
    print(f"{'key':15} {'category':10} {'sens':4}  label")
    for info in CATALOGUE:
        print(f"{info.key:15} {info.category:10} {info.sensitivity:4}  {info.label} — {info.description}")


def print_report(items: list[str]) -> None:
    a = analyse(items)
    label = lambda k: CATALOGUE_BY_KEY[k].label  # noqa: E731

    print("\nSHADOW — exposure report")
    print("=" * 60)
    print("Shared:", ", ".join(label(k) for k in sorted(a.selected)) or "(nothing)")
    print(f"\nExposure: {a.level}  ({a.score}/100)")
    b = a.breakdown
    print(f"  {b['items']} information points, {b['relationships']} relationships "
          f"({b['strong_relationships']} strong), {b['findings']} sensitive combinations "
          f"({b['high_findings']} high)")

    if a.findings:
        print("\nWhy these pieces are more revealing together:")
        for c in a.findings:
            names = " + ".join(label(k) for k in sorted(c.items))
            print(f"  [{SEVERITY_LABEL[c.severity]:6}] {c.title}: {names}")
            print(f"           {c.explanation}")

    if a.trace:
        print("\nTrace:", a.trace.summary)
        print("  " + " → ".join(label(k) for k in a.trace.path))
        for s in a.trace.steps:
            print(f"    {label(s.source)} → {label(s.target)}: {s.reason}")

    if a.what_if_remove:
        print("\nExperiment — remove one thing:")
        for w in a.what_if_remove[:3]:
            print(f"  − {w.label:24} → {w.score:3}/100 ({w.level}), change {w.delta:+}")
    if a.what_if_add:
        print("\nExperiment — add one thing:")
        for w in a.what_if_add[:3]:
            print(f"  + {w.label:24} → {w.score:3}/100 ({w.level}), change {w.delta:+}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SHADOW: what does your information reveal when connected?")
    parser.add_argument("items", nargs="*", help="catalogue keys that are public, e.g. school city schedule")
    parser.add_argument("--list", action="store_true", help="list every kind of information and exit")
    parser.add_argument("--json", action="store_true", help="print the full analysis as JSON")
    args = parser.parse_args(argv)

    if args.list:
        print_catalogue()
        return 0

    unknown = [k for k in args.items if k not in CATALOGUE_BY_KEY]
    if unknown:
        print(f"Unknown keys: {', '.join(unknown)}. Use --list to see valid ones.", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(analyse(args.items).to_dict(), indent=2, ensure_ascii=False))
    else:
        print_report(args.items)
    return 0


if __name__ == "__main__":
    sys.exit(main())
