"""Command-line interface: scan the local network, print what was found."""

from __future__ import annotations

import argparse
import json
import logging
import os
import pprint
import sys

from . import __version__
from .scanner import (
    MAX_SCAN_SECONDS,
    ScanConfig,
    ScanError,
    ScanResult,
    scan_network,
    to_jsonable,
)


def _positive_seconds(text: str) -> float:
    """Parse a seconds argument. The 3600 cap is an operational guard
    against typos, not a protocol limit; it matches MAX_SCAN_SECONDS
    so the CLI and the library API enforce the same bound."""
    try:
        value = float(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if not (0 < value <= MAX_SCAN_SECONDS):
        # Written this way (rather than two comparisons) so NaN is
        # rejected: both comparisons are false for NaN.
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
        # Choices come from the renderer registry, so a new format
        # cannot be added to one and forgotten in the other.
        choices=tuple(RENDERERS),
        default="text",
        help=(
            "text: summarised devices (default); "
            "json: structured result; "
            "raw: the original print_raw_data() dump"
        ),
    )
    parser.add_argument(
        "--no-descriptions",
        action="store_true",
        help=(
            "list recognised device types without fetching their info "
            "(skips get_info(); discover() itself may still fetch SSDP "
            "descriptions while matching types)"
        ),
    )
    parser.add_argument(
        "--output",
        metavar="FILE",
        default=None,
        help="write output to FILE instead of standard output",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="show debug logging (warnings are shown by default)",
    )
    return parser


def render_text(result: ScanResult) -> str:
    """Render a human-readable summary.

    The footer counts device types and info entries separately: the
    count is entries, not physical devices, and saying so avoids the
    old "Discovered N devices" wording, which overstated it.
    """
    lines = ["Discovered devices:"]
    for device in result.discovered:
        lines.append(f"{device.device_type}:")
        if device.error is not None:
            lines.append(f"  (error reading info: {device.error})")
        elif not device.info:
            if result.descriptions_included:
                lines.append("  (no info entries)")
            else:
                lines.append("  (descriptions skipped)")
        for entry in device.info:
            lines.append("  " + pprint.pformat(entry, width=88).replace("\n", "\n  "))
        lines.append("")
    lines.append(
        f"Discovered {len(result.discovered)} device type(s), "
        f"{result.discovered_count} info entries"
    )
    return "\n".join(lines) + "\n"


def render_json(result: ScanResult) -> str:
    """Render the structured result, with raw entries serialised."""
    payload = {
        "seconds": result.seconds,
        "discovered_count": result.discovered_count,
        "descriptions_included": result.descriptions_included,
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


# Registry of output formats. main() dispatches through this dict and
# build_parser() takes its choices from it, so adding a format is one
# entry here plus one test -- not a new branch in main().
RENDERERS = {"text": render_text, "json": render_json, "raw": render_raw}


def main(argv: list[str] | None = None) -> int:
    """Run the CLI. Exit codes: 0 scan done (even with zero devices),
    1 scan or output error, 2 bad arguments (argparse), 130 Ctrl-C."""
    args = build_parser().parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    config = ScanConfig(
        seconds=args.seconds,
        include_descriptions=not args.no_descriptions,
    )
    try:
        result = scan_network(config)
        rendered = RENDERERS[args.format](result)
        if args.output is not None:
            with open(args.output, "w", encoding="utf-8") as handle:
                handle.write(rendered)
        else:
            sys.stdout.write(rendered)
    except BrokenPipeError:
        # Piping to `head` closed the pipe; exit quietly instead of
        # printing a traceback (and a second one at shutdown).
        sys.stdout = open(os.devnull, "w")
        return 0
    except OSError as exc:
        # Covers --output paths that cannot be opened, among others.
        # BrokenPipeError is an OSError subclass and is handled above.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (ScanError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("scan interrupted", file=sys.stderr)
        return 130
    return 0
