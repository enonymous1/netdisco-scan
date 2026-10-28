# Changelog

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
