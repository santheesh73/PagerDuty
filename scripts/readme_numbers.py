#!/usr/bin/env python3
"""Keep the numbers in README.md true: measured by CI, never typed by hand.

Each number in the README sits between markers, `<!-- n:NAME -->650<!-- /n -->`. This script
measures every one it has a source for and either rewrites them (--write) or fails when the
README disagrees (--check, which CI runs).

    python3 scripts/readme_numbers.py --check \\
        --junit backend/pytest.xml --coverage backend/coverage.xml --vitest frontend/vitest.json

Sources:
  invariants      `### I<n>` headings in docs/INVARIANTS.md (and its index must list each one)
  mutations       entries in scripts/mutate.py's MUTATIONS
  backend_tests   tests in a pytest JUnit report (--junit)
  coverage        statement + branch coverage from coverage.xml (--coverage), the same total
                  `coverage report` prints and CI's --cov-fail-under gates; shown rounded, and
                  also the badge. --check accepts the README figure within one point of the
                  measurement, so a run landing on 94.9 instead of 95.1 does not fail a change
  frontend_tests  tests in a Vitest JSON report (--vitest)

A number without a source on this run (no --junit, say) is left alone, so each CI job checks the
ones it measured. Stdlib only.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
BADGE = ROOT / "docs" / "img" / "coverage.svg"
MARKER = re.compile(r"<!-- n:(?P<name>[a-z_]+) -->(?P<value>[^<]*)<!-- /n -->")


def invariants() -> int:
    text = (ROOT / "docs" / "INVARIANTS.md").read_text()
    headings = set(re.findall(r"^### (I\d+) ", text, flags=re.M))
    indexed = set(re.findall(r"^\| \[(I\d+)\]", text, flags=re.M))
    if headings != indexed:
        raise SystemExit(
            f"docs/INVARIANTS.md: the index and the sections disagree "
            f"(missing from index: {sorted(headings - indexed)}, "
            f"index without a section: {sorted(indexed - headings)})"
        )
    return len(headings)


def mutations() -> int:
    spec = importlib.util.spec_from_file_location("mutate", ROOT / "scripts" / "mutate.py")
    if spec is None or spec.loader is None:
        raise SystemExit("scripts/mutate.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["mutate"] = module
    spec.loader.exec_module(module)
    return len(module.MUTATIONS)


# The reports below are written by this repository's own CI run, not taken from outside.


def backend_tests(junit: Path) -> int:
    root = ET.parse(junit).getroot()  # noqa: S314
    suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
    # Every collected test, skipped or not: a local run without pg_dump 17 skips a few that CI runs.
    return sum(int(s.get("tests", 0)) for s in suites)


def coverage_percent(xml: Path) -> float:
    root = ET.parse(xml).getroot()  # noqa: S314
    covered = int(root.get("lines-covered", 0)) + int(root.get("branches-covered", 0))
    valid = int(root.get("lines-valid", 0)) + int(root.get("branches-valid", 0))
    return 100 * covered / valid if valid else 0.0


def frontend_tests(report: Path) -> int:
    return int(json.loads(report.read_text())["numTotalTests"])


def badge(percent: int) -> str:
    color = "#2ea44f" if percent >= 90 else "#dfb317" if percent >= 80 else "#e05d44"
    value = f"{percent}%"
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="104" height="20" role="img" aria-label="coverage: {value}">
  <title>coverage: {value}</title>
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/><stop offset="1" stop-opacity=".1"/></linearGradient>
  <clipPath id="r"><rect width="104" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)"><rect width="61" height="20" fill="#555"/><rect x="61" width="43" height="20" fill="{color}"/><rect width="104" height="20" fill="url(#s)"/></g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="110">
    <text x="315" y="140" transform="scale(.1)">coverage</text>
    <text x="815" y="140" transform="scale(.1)">{value}</text>
  </g>
</svg>
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="fail if README.md disagrees")
    mode.add_argument("--write", action="store_true", help="rewrite README.md (and the badge)")
    p.add_argument("--junit", type=Path, help="pytest --junitxml report")
    p.add_argument("--coverage", type=Path, help="coverage.xml")
    p.add_argument("--vitest", type=Path, help="vitest --reporter=json output")
    args = p.parse_args()

    measured: dict[str, float] = {"invariants": invariants(), "mutations": mutations()}
    if args.junit:
        measured["backend_tests"] = backend_tests(args.junit)
    if args.coverage:
        measured["coverage"] = coverage_percent(args.coverage)
    if args.vitest:
        measured["frontend_tests"] = frontend_tests(args.vitest)

    def shown(name: str) -> str:
        return f"{round(measured[name]):,}"

    def agrees(name: str, readme: str) -> bool:
        if name == "coverage":
            return readme.isdigit() and abs(int(readme) - measured[name]) < 1.0
        return readme == shown(name)

    text = README.read_text()
    found = {m["name"]: m["value"] for m in MARKER.finditer(text)}
    if missing := sorted(set(measured) - set(found)):
        print(f"README.md has no marker for: {', '.join(missing)}", file=sys.stderr)
        return 1

    stale = [(n, found[n], shown(n)) for n in measured if not agrees(n, found[n])]

    if args.write:
        new = MARKER.sub(
            lambda m: (
                f"<!-- n:{m['name']} -->{shown(m['name'])}<!-- /n -->"
                if m["name"] in measured
                else m[0]
            ),
            text,
        )
        README.write_text(new)
        if "coverage" in measured:
            BADGE.write_text(badge(round(measured["coverage"])))
        for name, old, value in stale:
            print(f"README.md {name}: {old} -> {value}")
        return 0

    for name, old, value in stale:
        print(f"README.md says {name} = {old}, measured {value}", file=sys.stderr)
    badge_stale = (
        "coverage" in measured
        and found["coverage"].isdigit()
        and (not BADGE.exists() or BADGE.read_text() != badge(int(found["coverage"])))
    )
    if badge_stale:
        print(f"docs/img/coverage.svg does not say {found['coverage']}%", file=sys.stderr)
    if stale or badge_stale:
        print(
            "Fix: make readme-numbers (or run this script with --write), commit.", file=sys.stderr
        )
        return 1
    print("README numbers match: " + ", ".join(f"{k}={shown(k)}" for k in sorted(measured)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
