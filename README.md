# Pulse

**Incident orchestration in the spirit of PagerDuty — alerts in, the right human paged, every action on the record.**

[![CI](https://github.com/santheesh73/PagerDuty/actions/workflows/ci.yml/badge.svg)](https://github.com/santheesh73/PagerDuty/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

> 🚧 Under active construction. See the commit history for progress.

## Quick start

```bash
git clone https://github.com/santheesh73/PagerDuty.git pulse && cd pulse
cp .env.example .env
make up          # → http://localhost:5173
make check       # lint + typecheck + tests + migration drift
```

Stack and pinned versions: [`docs/STACK.md`](docs/STACK.md).
