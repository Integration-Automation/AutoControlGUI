# What's New — AutoControl

**This log has moved to [`docs/updates/`](docs/updates/README.md).** Every former
`## What's new (…)` section of this file is now one `#release` entry there, in a
monthly batch file (`docs/updates/YYYY-MM.md`), next to every other piece of
finished work. Each section's text was carried over unchanged except that its
headings moved down one level. This file stays so that existing links still land
somewhere.

- **Index, newest first, with the query commands**: [docs/updates/README.md](docs/updates/README.md)
- **Every entry, one line each** (from the repository root): `rg -n "^## U-2" docs/updates`
- **Release notes only**: `rg -n "^## U-2.*#release" docs/updates`
- **One month**: `rg -n "^## U-202608" docs/updates`
- **The full text of one entry**: `rg -n -A 60 "^## U-20260824-01" docs/updates`

Without `rg`: `git grep -n "^## U-2" -- docs/updates`.

**Finding an old section**: `What's new (YYYY-MM-DD)` became entry `U-YYYYMMDD-01`.
The two sections dated only by month got the day their last content was added:
`What's new (2026-06)` is `U-20260605-01` and `What's new (2026-05)` is `U-20260525-01`.

Compatibility changes are still recorded in [CHANGELOG.md](CHANGELOG.md); open work
is in [Progress.md](Progress.md). The older translated notes (through 2026-08-20) are
[README/WHATS_NEW_zh-TW.md](README/WHATS_NEW_zh-TW.md) and
[README/WHATS_NEW_zh-CN.md](README/WHATS_NEW_zh-CN.md).
