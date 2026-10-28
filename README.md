# netdisco-scan

Scan the local network for devices and services — mDNS (Chromecast, HomeKit, …) and SSDP/UPnP — and print what was found, as summarised devices, structured JSON, or the raw discovery dump.

This is v2.0.0, a modernisation of a 21-line script that only printed the raw dump. The original script is preserved in the project history note in [CHANGELOG.md](CHANGELOG.md); no code or history from it is carried into this export beyond its behaviour.

## Quick start

```bash
pip install .
netdisco-scan
```

```text
Discovered devices:
google_cast:
  ('Living Room.local.', 8009)

Discovered 1 devices
```

The wait defaults to 5 seconds. Longer waits catch slow responders:

```bash
netdisco-scan --seconds 15
netdisco-scan --format json > scan.json
netdisco-scan --format raw        # the original print_raw_data() dump
python -m netdisco_scan --seconds 10 --format json
```

## Output formats

- **text** (default): one section per recognised device type, with the info netdisco returns for it, plus a total. A type whose info cannot be read is shown with its error instead of failing the scan.
- **json**: `{"seconds": …, "discovered_count": …, "discovered": [{"type": …, "info": […], "error": …}], "raw": {"zeroconf": […], "ssdp": […]}}`. SSDP raw entries contribute only their header values; serialising a result never fetches a device description.
- **raw**: the v1 behaviour — the Zeroconf cache, then the SSDP entries, pretty-printed. This is the only format that shows devices netdisco does not recognise as a named type (see below).

Exit codes: `0` for a completed scan (even with zero devices), `1` for a scan error, `2` for bad arguments, `130` if interrupted with Ctrl-C. Discovery is always stopped before exit, including on interruption.

## How it works

`netdisco_scan.scan_network(seconds)` creates a `netdisco.discovery.NetworkDiscovery`, scans, waits, then — before stopping — captures the raw mDNS/SSDP entries and calls `discover()` / `get_info()` per device type. Each type is isolated: if reading one type's info raises, that type is recorded with its error and the rest of the scan continues.

Two upstream behaviours worth knowing:

- Reading a type's info can fetch that device's description document over HTTP (that is how netdisco fills in names and model numbers). It is cached per entry, but a scan on a network with many UPnP devices can take longer than `--seconds` while those fetches complete.
- In netdisco 3.0.0 only eight named types are recognised by `discover()` (Bluesound, Bose SoundTouch, Enigma2, Frontier Silicon, LG, OpenHome, SABnzbd, Yamaha). Most devices you expect — Chromecast, Hue, WeMo, DLNA renderers — appear only in the raw dump. Use `--format raw` (or the `raw` section of `--format json`) if the summarised list looks empty on a network you know has devices.

## The netdisco dependency, honestly

`netdisco` is **deprecated upstream**: its maintainers state they "will no longer release new versions, fix bugs or accept pull requests" and point Home Assistant integrations at the `zeroconf` and SSDP manifest options instead. This package pins `netdisco==3.0.0`, the last release, deliberately — the pinned version is the behaviour that was verified. If a maintained replacement is ever wanted, the rewrite surface is small: `netdisco_scan.scanner` is the only module that touches netdisco, behind a factory function, and the test suite already runs against fake discoveries. A `zeroconf` + SSDP rewrite would keep the CLI and output formats unchanged.

## Requirements

- Python 3.10+
- A local network. Discovery is LAN-only multicast/broadcast traffic (mDNS on UDP 5353, SSDP on 239.255.255.250:1900); it sends nothing to the internet. Some networks (guest isolation, VPNs, multicast filtering) will simply find nothing.
- No special permissions are normally needed. If your firewall blocks multicast, discovery will return empty rather than error.

## Privacy

A scan reveals your LAN: device names, hostnames, IP addresses, and device description URLs. Treat `--format raw` and `--format json` output like a network inventory — do not paste it into a public issue or post.

## Development

```bash
pip install ".[dev]"
ruff check .
pytest
```

Tests use fake discoveries and never touch the network; the only live check is running `netdisco-scan` on a real LAN and confirming it exits 0. CI runs ruff + pytest on Ubuntu and Windows, Python 3.10–3.12.

## License

MIT. See [LICENSE](LICENSE).
