#!/usr/bin/env bash
# Re-record the README's demo GIF (docs/img/demo.gif) and the repository's social preview
# (docs/img/social-preview.png) from the real app, so neither goes stale.
#
#   ./scripts/record_demo.sh                    against a seeded stack on http://localhost:8080
#                                               (docker-compose.prod.yml with SEED_DEMO=1)
#   TICK_SECRET=... ./scripts/record_demo.sh    the one-container demo (docker-compose.demo.yml)
#                                               has no Beat, so the recording drives its ticks
#   BASE_URL=... OUT=... ./scripts/record_demo.sh   another address, another output file
#
# Records one take with Playwright (e2e/demo/record.spec.ts, screenshots at about 8 fps, the minute
# spent waiting for the escalation thinned to one frame in twelve), then joins the frames into a
# 960 px GIF with one optimised palette. Needs Node, ffmpeg and a Playwright Chromium
# (PW_CHROMIUM_PATH works too).
set -euo pipefail
cd "$(dirname "$0")/.."

OUT=${OUT:-docs/img/demo.gif}
FRAMES=e2e/demo-results/frames
rm -rf e2e/demo-results
(cd e2e && npx playwright test --config demo/playwright.config.ts)
count=$(find "$FRAMES" -name 'frame-*.png' | wc -l)
[ "$count" -gt 0 ] || { echo "no frames recorded"; exit 1; }

ffmpeg -hide_banner -loglevel error -y -framerate 8 -i "$FRAMES/frame-%05d.png" -vf \
  "scale=960:-1:flags=lanczos,split[x][y];[x]palettegen=max_colors=128:stats_mode=diff[p];[y][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle" \
  "$OUT"
echo "wrote $OUT ($(du -h "$OUT" | cut -f1), $count frames) and docs/img/social-preview.png"
