#!/usr/bin/env python3
"""Write docs/img/coverage.svg from the backend's last coverage run.

Self-contained on purpose: no third-party badge service, so it renders the same in a
private repo, a fork, or offline. Run via `make badge` after `make test-backend`.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def total_percent() -> float:
    out = subprocess.run(
        ["uv", "run", "coverage", "json", "-o", "-", "-q"],
        cwd=ROOT / "backend", capture_output=True, text=True, check=True,
    ).stdout
    return float(json.loads(out)["totals"]["percent_covered"])


def badge(percent: float) -> str:
    color = "#2ea44f" if percent >= 90 else "#dfb317" if percent >= 80 else "#e05d44"
    value = f"{percent:.0f}%"
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


if __name__ == "__main__":
    percent = total_percent()
    target = ROOT / "docs" / "img" / "coverage.svg"
    target.write_text(badge(percent))
    print(f"coverage {percent:.1f}% → {target.relative_to(ROOT)}")
    sys.exit(0)
