"""Command-line interface: scan the local network, print what was found."""

from __future__ import annotations

import argparse
import json
import pprint
import sys

from .scanner import ScanError, ScanResult, scan_network, to_jsonable

__version__ = "2.0.0"


def _positive_seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if value <= 0 or value > 3600:
        raise argparse.ArgumentTypeError("seconds must be > 0 and <= 3600")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netdisco-scan",
        description=(
            "Scan the local network for devices and services "
            "(mDNS + SSDP, via netdisco 3.0.0) and print what was found."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_argument(
        "--seconds",
        type=_positive_seconds,
        default=5.0,
        metavar="SECONDS",
        help="how long to listen for replies (default: 5)",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "raw"),
        default="text",
        help=(
            "text: summarised devices (default); "
            "json: structured result; "
            "raw: the original print_raw_data() dump"
        ),
    )
    return parser


def render_text(result: ScanResult) -> str:
    lines = ["Discovered devices:"]
    for device in result.discovered:
        lines.append(f"{device.device_type}:")
        if device.error is not None:
            lines.append(f"  (error reading info: {device.error})")
        for entry in device.info:
            lines.append("  " + pprint.pformat(entry, width=88).replace("\n", "\n  "))
        lines.append("")
    lines.append(f"Discovered {result.discovered_count} devices")
    return "\n".join(lines) + "\n"


def render_json(result: ScanResult) -> str:
    payload = {
        "seconds": result.seconds,
        "discovered_count": result.discovered_count,
        "discovered": [
            {
                "type": device.device_type,
                "info": to_jsonable(device.info),
                "error": device.error,
            }
            for device in result.discovered
        ],
        "raw": {
            "zeroconf": to_jsonable(result.zeroconf_entries),
            "ssdp": to_jsonable(result.ssdp_entries),
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def render_raw(result: ScanResult) -> str:
    """The v1 behaviour: Zeroconf cache, then SSDP entries, pretty-printed."""
    parts = ["Zeroconf", pprint.pformat(result.zeroconf_entries), "", "SSDP"]
    parts.append(pprint.pformat(result.ssdp_entries))
    return "\n".join(parts) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = scan_network(args.seconds)
    except ScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("scan interrupted", file=sys.stderr)
        return 130
    if args.format == "json":
        sys.stdout.write(render_json(result))
    elif args.format == "raw":
        sys.stdout.write(render_raw(result))
    else:
        sys.stdout.write(render_text(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
