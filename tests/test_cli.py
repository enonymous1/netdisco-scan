"""Tests for the CLI: formats, argument validation, exit codes."""

from __future__ import annotations

import json

import pytest

from netdisco_scan import cli
from netdisco_scan.scanner import DiscoveredDevice, ScanError, ScanResult


def _result():
    return ScanResult(
        seconds=5.0,
        discovered=[
            DiscoveredDevice("google_cast", [("Living Room.local.", 8009)]),
            DiscoveredDevice("broken_type", [], error="boom"),
        ],
        zeroconf_entries=[],
        ssdp_entries=[],
    )


def test_text_output_lists_devices_and_count(monkeypatch, capsys):
    monkeypatch.setattr(cli, "scan_network", lambda seconds: _result())
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "google_cast:" in out
    assert "Living Room.local." in out
    assert "Discovered 1 devices" in out
    assert "error reading info: boom" in out


def test_text_output_empty_scan(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "scan_network", lambda seconds: ScanResult(seconds=5.0)
    )
    assert cli.main([]) == 0
    assert "Discovered 0 devices" in capsys.readouterr().out


def test_json_output_parses_and_is_structured(monkeypatch, capsys):
    monkeypatch.setattr(cli, "scan_network", lambda seconds: _result())
    assert cli.main(["--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["discovered_count"] == 1
    assert payload["discovered"][0]["type"] == "google_cast"
    assert payload["discovered"][0]["info"] == [["Living Room.local.", 8009]]
    assert payload["discovered"][1]["error"] == "boom"
    assert payload["raw"] == {"zeroconf": [], "ssdp": []}


def test_raw_output_matches_v1_dump_shape(monkeypatch, capsys):
    monkeypatch.setattr(cli, "scan_network", lambda seconds: _result())
    assert cli.main(["--format", "raw"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Zeroconf\n")
    assert "\nSSDP\n" in out


def test_invalid_seconds_rejected():
    for bad in ("0", "-1", "abc", "99999"):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["--seconds", bad])
        assert excinfo.value.code == 2


def test_invalid_format_rejected():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--format", "yaml"])
    assert excinfo.value.code == 2


def test_scan_error_exits_1(monkeypatch, capsys):
    def fail(_seconds):
        raise ScanError("no network")

    monkeypatch.setattr(cli, "scan_network", fail)
    assert cli.main([]) == 1
    assert "error: no network" in capsys.readouterr().err


def test_keyboard_interrupt_exits_130(monkeypatch, capsys):
    def interrupted(_seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "scan_network", interrupted)
    assert cli.main([]) == 130
    assert "interrupted" in capsys.readouterr().err


def test_help_and_version():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
