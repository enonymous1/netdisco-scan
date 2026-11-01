"""Tests for the CLI: formats, argument validation, exit codes."""

from __future__ import annotations

import json
import sys

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
    monkeypatch.setattr(cli, "scan_network", lambda config: _result())
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "google_cast:" in out
    assert "Living Room.local." in out
    # Footer counts types and entries separately, not "N devices".
    assert "Discovered 2 device type(s), 1 info entries" in out
    assert "error reading info: boom" in out


def test_text_output_empty_scan(monkeypatch, capsys):
    monkeypatch.setattr(
        cli, "scan_network", lambda config: ScanResult(seconds=5.0)
    )
    assert cli.main([]) == 0
    assert "Discovered 0 device type(s), 0 info entries" in capsys.readouterr().out


def test_text_output_no_descriptions(monkeypatch, capsys):
    result = ScanResult(
        seconds=5.0,
        discovered=[DiscoveredDevice("yamaha", [])],
        descriptions_included=False,
    )
    monkeypatch.setattr(cli, "scan_network", lambda config: result)
    assert cli.main([]) == 0
    assert "(descriptions skipped)" in capsys.readouterr().out


def test_json_output_parses_and_is_structured(monkeypatch, capsys):
    monkeypatch.setattr(cli, "scan_network", lambda config: _result())
    assert cli.main(["--format", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["discovered_count"] == 1
    assert payload["descriptions_included"] is True
    assert payload["discovered"][0]["type"] == "google_cast"
    assert payload["discovered"][0]["info"] == [["Living Room.local.", 8009]]
    assert payload["discovered"][1]["error"] == "boom"
    assert payload["raw"] == {"zeroconf": [], "ssdp": []}


def test_raw_output_matches_v1_dump_shape(monkeypatch, capsys):
    monkeypatch.setattr(cli, "scan_network", lambda config: _result())
    assert cli.main(["--format", "raw"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Zeroconf\n")
    assert "\nSSDP\n" in out


def test_seconds_and_flags_reach_scan_network(monkeypatch):
    seen = {}

    def capture(config):
        seen["config"] = config
        return _result()

    monkeypatch.setattr(cli, "scan_network", capture)
    assert cli.main(["--seconds", "7"]) == 0
    assert seen["config"].seconds == 7.0
    assert seen["config"].include_descriptions is True
    assert cli.main(["--no-descriptions"]) == 0
    assert seen["config"].include_descriptions is False


def test_output_file_and_unwritable_output(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "scan_network", lambda config: _result())
    target = tmp_path / "scan.txt"
    assert cli.main(["--output", str(target)]) == 0
    assert "Discovered 2 device type(s)" in target.read_text(encoding="utf-8")
    assert capsys.readouterr().out == ""
    # A missing parent directory is a clean exit 1, not a traceback.
    assert cli.main(["--output", str(tmp_path / "nope" / "scan.txt")]) == 1
    assert "error:" in capsys.readouterr().err


def test_broken_pipe_exits_quietly(monkeypatch):
    class _BrokenStdout:
        def write(self, _text):
            raise BrokenPipeError

        def flush(self):
            pass

    monkeypatch.setattr(sys, "stdout", _BrokenStdout())
    monkeypatch.setattr(cli, "scan_network", lambda config: _result())
    assert cli.main([]) == 0


def test_renderer_registry_matches_parser_choices():
    assert tuple(cli.RENDERERS) == ("text", "json", "raw")
    parser = cli.build_parser()
    fmt_action = next(a for a in parser._actions if a.dest == "format")
    assert tuple(fmt_action.choices) == tuple(cli.RENDERERS)


def test_invalid_seconds_rejected():
    for bad in ("0", "-1", "abc", "99999", "nan", "inf"):
        with pytest.raises(SystemExit) as excinfo:
            cli.main(["--seconds", bad])
        assert excinfo.value.code == 2


def test_invalid_format_rejected():
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--format", "yaml"])
    assert excinfo.value.code == 2


def test_scan_error_exits_1(monkeypatch, capsys):
    def fail(_config):
        raise ScanError("no network")

    monkeypatch.setattr(cli, "scan_network", fail)
    assert cli.main([]) == 1
    assert "error: no network" in capsys.readouterr().err


def test_keyboard_interrupt_exits_130(monkeypatch, capsys):
    def interrupted(_config):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "scan_network", interrupted)
    assert cli.main([]) == 130
    assert "interrupted" in capsys.readouterr().err


def test_help_and_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
    assert "netdisco-scan" in capsys.readouterr().out


def test_version_is_single_sourced():
    from importlib.metadata import PackageNotFoundError, version

    from netdisco_scan import __version__ as package_version

    try:
        installed = version("netdisco-scan")
    except PackageNotFoundError:
        pytest.skip("package not installed; version falls back to unknown")
    assert cli.__version__ == package_version == installed
