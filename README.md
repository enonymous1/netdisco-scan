# netdisco-scan

[![CI](https://github.com/enonymous1/netdisco-scan/actions/workflows/ci.yml/badge.svg)](https://github.com/enonymous1/netdisco-scan/actions/workflows/ci.yml)
[![Python 3.10–3.12](https://img.shields.io/badge/python-3.10%E2%80%933.12-blue)](https://github.com/enonymous1/netdisco-scan)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

<!-- Visual slot (hero): insert docs/assets/screenshots/text-output.png
     here once it is captured from a real LAN run and redacted to
     TEST-NET (192.0.2.0/24). Do not fabricate it. -->

## Description

`netdisco-scan` is a small command-line tool that listens for devices
announcing themselves on your local network and prints what it finds.
It is a **passive** scanner: it sends mDNS and SSDP discovery traffic
and reports replies. It is not a port scanner, not a replacement for
Nmap, and it never touches hosts that do not answer discovery.

It reports in three formats:

- **text** (default): one section per recognised device type, with the
  information netdisco returns for it, plus a total.
- **json**: a structured result for scripts and further processing.
- **raw**: the unprocessed Zeroconf cache and SSDP entries, pretty-printed.

Example (illustrative output; addresses are from TEST-NET, not a real LAN):

```text
$ netdisco-scan --seconds 10
Discovered devices:
yamaha:
  {'host': '192.0.2.10', 'port': 80,
   'ssdp_description': 'http://192.0.2.10/description.xml'}

Discovered 1 device type(s), 1 info entries
```

Two limitations to know before you use it:

- In netdisco 3.0.0, `discover()` recognises only eight named device
  types (Bluesound, Bose SoundTouch, Enigma2, Frontier Silicon, LG,
  OpenHome, SABnzbd, Yamaha). Most devices on a typical home network
  appear only in the **raw** output. If the text output looks empty on
  a network you know has devices, check `--format raw` first.
- `netdisco` is **deprecated upstream**: its maintainers state they
  will no longer release new versions, fix bugs, or accept pull
  requests. This package pins `netdisco==3.0.0`, the last release,
  deliberately, and the pinned version is the behaviour that was
  verified. A rewrite on maintained `zeroconf` + SSDP libraries is the
  planned replacement path; it would keep the CLI and output formats
  unchanged.

Exit codes: `0` for a completed scan (even with zero devices), `1` for
a scan or output error, `2` for bad arguments, `130` if interrupted
with Ctrl-C.

## Prerequisites

- Python 3.10, 3.11, or 3.12. Python 3.13+ is not tested by CI yet;
  anything newer is untested, not known-broken.
- `git` and `pip` (or `pipx`, see Installation).
- A local network you are allowed to scan. Discovery is LAN-only
  multicast/broadcast traffic (mDNS on UDP 5353, SSDP to
  239.255.255.250:1900); it sends nothing to the internet.
- No administrator or root privileges are normally needed. A VPN,
  guest-network isolation, or a firewall blocking multicast will
  typically produce an empty result, not an error — see
  Troubleshooting.

## Installation

This package is not on PyPI yet. Install from a checkout:

```bash
git clone https://github.com/enonymous1/netdisco-scan.git
cd netdisco-scan
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
```

Or with `pipx` (isolated, no venv to manage):

```bash
pipx install git+https://github.com/enonymous1/netdisco-scan.git
```

Verify the install:

```bash
netdisco-scan --version
netdisco-scan --help
python -m netdisco_scan --help   # module form, same CLI
```

## Usage

```bash
netdisco-scan                          # 5-second text scan (default)
netdisco-scan --seconds 15             # listen longer for slow responders
netdisco-scan --format json > scan.json
netdisco-scan --format raw             # raw Zeroconf + SSDP dump
netdisco-scan --no-descriptions        # list types, skip get_info() fetches
netdisco-scan --output scan.txt        # write to a file instead of stdout
netdisco-scan --verbose                # show debug logging
```

<!-- Visual slot (demo GIF): insert docs/assets/demo/scan-demo.gif
     here once recorded (asciinema or terminalizer) from a real
     10-second run, ending on the text output. -->

<!-- Visual slot (JSON screenshot): insert
     docs/assets/screenshots/json-output.png here, from the same run
     as the hero screenshot, showing the JSON structure. -->

### Output shapes

Text output lists recognised types only. JSON output always contains
both views:

```json
{
  "seconds": 10.0,
  "discovered_count": 1,
  "descriptions_included": true,
  "discovered": [{"type": "yamaha", "info": [], "error": null}],
  "raw": {"zeroconf": [], "ssdp": []}
}
```

Note that `discovered_count` counts info entries, not physical
devices: one device type with three info entries counts as three,
and the text footer says so ("1 device type(s), 1 info entries").
The raw section is the complete view; the text section is the
recognised subset.

`--no-descriptions` lists recognised types with empty info and
`descriptions_included: false`. It skips the `get_info()` fetches
only: `discover()` itself may still fetch SSDP descriptions while
matching device types (upstream netdisco behaviour), so it reduces,
but does not eliminate, description traffic.

## Architecture

```text
CLI (argparse) ──> ScanConfig ──> scan_network
                                       │
                                       ▼
                         Netdisco adapter ──> NetworkDiscovery (netdisco 3.0.0)
                                       │                    │
                                       │                    ├── mDNS (Zeroconf cache)
                                       │                    └── SSDP (UPNP entries)
                                       ▼
                         ScanResult ──> renderer registry (text / json / raw)
```

<!-- Visual slot (diagram): insert
     docs/assets/diagrams/architecture.svg here, a plain box-and-arrow
     diagram with exactly the five boxes above and no vendor logos. -->

`netdisco_scan.scan_network(config)` creates a discovery object
through the `NetdiscoDiscoveryAdapter`, scans, waits `config.seconds`,
then — before stopping — captures the raw entries and calls
`discover()` / `get_info()` per device type. Each type is isolated:
if reading one type's info raises, that type is recorded with its
error and the rest of the scan continues. Discovery is always stopped,
including on Ctrl-C, and a stop failure is logged rather than raised.

The `Discovery` protocol (`src/netdisco_scan/scanner.py`) is the seam
for the planned zeroconf-native backend: it replaces the adapter, not
the scanner or the CLI. Output formats are a registry
(`RENDERERS` in `src/netdisco_scan/cli.py`); adding one is one
registry entry plus one test.

One timing fact matters: `seconds` is the listen time, not a total
time budget. Reading a type's info can fetch that device's description
document over HTTP, so a scan on a network with many UPnP devices can
take longer than `--seconds` while those fetches complete. The fetches
run sequentially today; parallelising them is a known improvement, not
a promised behaviour.

## Local Development

```bash
git clone https://github.com/enonymous1/netdisco-scan.git
cd netdisco-scan
python -m venv .venv
source .venv/bin/activate        # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
ruff check .
mypy src/netdisco_scan
pytest
```

What the test suite does and does not do:

- Tests use fake discoveries and never touch the network. That is
  deliberate: CI has no LAN to scan.
- The only live check is running `netdisco-scan` on a real LAN and
  confirming it exits 0 and returns plausible output. Run that before
  every release; CI cannot do it for you.
- To add an output format, add a renderer to `RENDERERS` in
  `src/netdisco_scan/cli.py` and a test in `tests/test_cli.py`
  asserting its exact output. To change scan behaviour, change
  `src/netdisco_scan/scanner.py` and `tests/test_scanner.py`
  together; the fakes there are the contract for the discovery
  interface.

Before pushing, run `ruff check .`, `mypy src/netdisco_scan`, and
`pytest` from a clean checkout, and confirm `git status` is clean.
The project uses LF line endings (see `.gitattributes`).

## Deployment

For a command-line tool, "deployment" means a tagged release, not a
server deploy. The current release process is:

1. Update `CHANGELOG.md` and the version in `pyproject.toml`
   (the package version is the single source of truth; the CLI reads
   it from installed metadata).
2. Commit, tag (`git tag v2.1.0`), and push the tag.
3. GitHub Actions (`.github/workflows/ci.yml`) runs ruff, mypy, and
   pytest on Ubuntu and Windows, Python 3.10–3.12.
4. Write release notes from the CHANGELOG entry.

Not done yet, and stated as such rather than implied:

- The package is not published to PyPI. Publishing would be
  `python -m build` followed by `twine upload dist/*` from a clean
  checkout, after adding a PyPI trusted publisher or API token in the
  repository settings.
- There is no Windows installer, Homebrew formula, or container image.
  `pipx install git+https://github.com/enonymous1/netdisco-scan.git`
  is the supported install path until PyPI publishing lands.

## Troubleshooting

**The scan finds nothing.** Check, in order: (1) you are on the same
network as the devices (not a VPN, not a guest network with client
isolation); (2) your firewall allows multicast; (3) `--format raw`
shows anything at all — if raw is empty, nothing answered discovery;
if raw has entries but text is empty, the devices are simply not among
the eight recognised types.

<!-- Visual slot (raw screenshot): insert
     docs/assets/screenshots/raw-output.png here, a raw dump from a
     run where text output is empty, as the proof for the
     "check raw first" advice above. -->

**The scan takes longer than `--seconds`.** That is expected when
many UPnP devices are present: description fetches run after the
listen window. See Architecture.

**`netdisco-scan --help` works but a scan fails with
"netdisco is not installed".** The package was installed without its
dependencies (for example, with `pip install --no-deps`). Reinstall
with `python -m pip install .`.

**`--seconds nan` or a huge value.** Both are rejected with exit 2
(argparse) or a clean exit 1 from the library API; seconds must be
finite and in (0, 3600].

## Privacy

A scan reveals your LAN: device names, hostnames, IP addresses, and
device description URLs. Treat `--format raw` and `--format json`
output like a network inventory — do not paste it into a public issue
or post. The screenshots and demo planned for this README use TEST-NET
addresses (192.0.2.0/24) for exactly that reason.

## License

MIT. See [LICENSE](LICENSE). Changes are recorded in
[CHANGELOG.md](CHANGELOG.md).
