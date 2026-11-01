# Changelog

## 2.1.0 — 2026-11-01

Staff-review fixes (review delivered 2026-10-31 against v2.0.0),
applied as a follow-up commit on top of v2.0.0 — not a re-squash.
v2.0.0 was never pushed, so the first push carries both commits.

- P0 fixed: `--seconds nan`/`inf` no longer pass validation and then
  fail inside `sleep()` — validation is now a shared finite check
  with a shared `MAX_SCAN_SECONDS = 3600` constant, enforced by both
  the CLI and the `scan_network` API (which previously had no cap).
- P0 fixed: README example corrected — the old `google_cast` text
  output was impossible in netdisco 3.0.0 (only eight discoverables);
  the example now uses a Yamaha device with TEST-NET addresses.
- P0 fixed: silent failures are no longer silent — mDNS/SSDP capture
  failures and stop failures log warnings, and `--verbose` enables
  debug logging (warnings are shown by default).
- Error model: `DependencyError` (missing netdisco) and
  `DiscoveryError` (failed/non-list `discover()`), both subclassing
  `ScanError`; the CLI also exits 1 cleanly on `ValueError` and
  output errors, and exits 0 quietly on `BrokenPipeError` (piping
  to `head`).
- Architecture: explicit `Discovery` protocol plus
  `NetdiscoDiscoveryAdapter` (the seam for a future zeroconf-native
  backend), frozen `ScanConfig`, and a renderer registry
  (`RENDERERS`) that also drives the `--format` choices.
- New flags: `--no-descriptions` (list types, skip `get_info()`
  fetches; `discover()` itself may still fetch SSDP descriptions
  while matching types — documented, not hidden) and `--output FILE`.
- Text footer now counts honestly ("N device type(s), M info
  entries"); JSON gains `descriptions_included`. `to_jsonable`
  maps non-finite floats to `null` (valid strict JSON) and keeps the
  first value on dict-key stringification collisions, with a warning.
- Version is now single-sourced from `pyproject.toml` via installed
  metadata (`__init__.py` reads it; `cli.py` no longer hardcodes it),
  with a `py.typed` marker and a non-strict mypy gate in CI
  (plus pip caching and a job timeout). `__init__` now also exports
  `DiscoveredDevice` and `to_jsonable`.
- README rewritten with Description, Prerequisites, Installation,
  Local Development, and Deployment sections, plus Usage,
  Architecture, Troubleshooting, and Privacy. The five planned visual
  assets (hero screenshot, demo GIF, JSON screenshot, architecture
  diagram, raw screenshot) are marked as slots in the README, not
  shipped: they must be captured from real runs, redacted to TEST-NET,
  and never fabricated.
- Deliberately deferred (not silently dropped): parallel `get_info()`
  fetches (netdisco thread-safety unverified), a lockfile for the
  floating transitive deps (`zeroconf`/`requests` still float under
  the pinned `netdisco==3.0.0`), a Python 3.13 CI leg (unverified
  locally), and a `ruff format --check` gate. A live scan on a real
  LAN with devices is still unverified — his network is the gate.

## 2.0.0 — 2026-10-28

Squashed public export. The v1 project was a single 21-line script
(`discovery.py`, February 2026) that created a `NetworkDiscovery`, slept
5 seconds, printed the raw dump with `print_raw_data()`, and stopped.
That script, its README, and the stock `.gitignore` are not carried into
this export's history; only its behaviour is preserved as `--format raw`.
Renamed from `ss-netdisco` to `netdisco-scan` before any push (the
superseded `ss-netdisco` export must not be pushed); package
`ss_netdisco` -> `netdisco_scan`, no behaviour change.

- Installable package `netdisco_scan` with the `netdisco-scan`
  console script and `python -m netdisco_scan`; `netdisco==3.0.0` pinned
  (the last, deprecated upstream release — see README).
- `--seconds` (validated, 0 < s <= 3600) and `--format text|json|raw`;
  the default text format now actually calls `discover()` /
  `get_info()`, which v1 never did.
- Discovery is always stopped (try/finally), including on Ctrl-C
  (exit 130); scan errors exit 1, bad arguments exit 2.
- Raw mDNS/SSDP entries are captured before `stop()` clears the mDNS
  side, so the raw dump is complete; per-device-type `get_info()`
  failures are recorded per type instead of failing the scan.
- JSON output is fully serialisable (bytes, datetimes, sets, and
  unknown objects converted) and never fetches device descriptions
  during serialisation.
- Focused `.gitignore`, LF `.gitattributes`, MIT LICENSE, CI
  (Ubuntu + Windows, Python 3.10–3.12), 20 tests with fake
  discoveries — no network access in the test suite.
