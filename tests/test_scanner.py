"""Tests for the scanner core, using fake discoveries (no network)."""

from __future__ import annotations

import logging
import math
import sys
from datetime import datetime, timezone

import pytest

from netdisco_scan.scanner import (
    DependencyError,
    NetdiscoDiscoveryAdapter,
    ScanConfig,
    ScanError,
    ScanResult,
    scan_network,
    to_jsonable,
)


class FakeEntry:
    """Stand-in for a Zeroconf DNS record: only its repr matters."""

    def __init__(self, text):
        self.text = text

    def __repr__(self):
        return f"<FakeEntry {self.text}>"


class FakeSsdpEntry:
    """Stand-in for a UPNPEntry: header values, no description fetch."""

    def __init__(self, values):
        self.values = values
        self.description_fetched = False

    @property
    def description(self):  # pragma: no cover - must never be touched
        self.description_fetched = True
        return {}

    def __repr__(self):
        return f"<FakeSsdpEntry {self.values.get('location', '')}>"


class FakeMdns:
    def __init__(self, entries, broken=False):
        self._entries = entries
        self.broken = broken

    @property
    def entries(self):
        if self.broken:
            raise RuntimeError("zeroconf not started")
        return self._entries


class FakeSsdp:
    def __init__(self, entries):
        self.entries = entries


class FakeDiscovery:
    def __init__(self, infos=None, *, zeroconf_entries=None, ssdp_entries=None,
                 info_errors=None, discover_error=None, stop_error=False,
                 mdns_broken=False):
        self.infos = infos or {}
        self.info_errors = info_errors or {}
        self.discover_error = discover_error
        self.stop_error = stop_error
        self.scanned = False
        self.stopped = False
        self.mdns = FakeMdns(zeroconf_entries or [], broken=mdns_broken)
        self.ssdp = FakeSsdp(ssdp_entries or [])

    def scan(self):
        self.scanned = True

    def discover(self):
        if self.discover_error is not None:
            raise self.discover_error
        return list(self.infos)

    def get_info(self, device_type):
        if device_type in self.info_errors:
            raise self.info_errors[device_type]
        return self.infos[device_type]

    def stop(self):
        self.stopped = True
        if self.stop_error:
            raise RuntimeError("stop failed")


def run(fake, seconds=5.0, sleep=None):
    calls = []

    def fake_sleep(value):
        calls.append(value)
        if sleep is not None:
            sleep(value)

    result = scan_network(seconds, discovery_factory=lambda: fake, sleep=fake_sleep)
    return result, calls


def test_scan_returns_discovered_info_and_raw_entries():
    fake = FakeDiscovery(
        {"google_cast": [("Living Room.local.", 8009)]},
        zeroconf_entries=[FakeEntry("a")],
        ssdp_entries=[
            FakeSsdpEntry(
                {"location": "http://192.0.2.1/desc.xml", "st": "upnp:rootdevice"}
            )
        ],
    )
    result, calls = run(fake, seconds=2.5)
    assert fake.scanned and fake.stopped
    assert calls == [2.5]
    assert result.seconds == 2.5
    assert [d.device_type for d in result.discovered] == ["google_cast"]
    assert result.discovered[0].info == [("Living Room.local.", 8009)]
    assert result.discovered[0].error is None
    assert result.discovered_count == 1
    assert [repr(e) for e in result.zeroconf_entries] == ["<FakeEntry a>"]
    assert result.ssdp_entries[0].values["st"] == "upnp:rootdevice"


def test_stop_called_when_discover_raises():
    fake = FakeDiscovery(discover_error=RuntimeError("needs start"))
    with pytest.raises(ScanError, match="discovery failed"):
        run(fake)
    assert fake.stopped


def test_stop_called_when_sleep_is_interrupted():
    fake = FakeDiscovery()

    def boom(_seconds):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run(fake, sleep=boom)
    assert fake.stopped


def test_one_bad_device_type_does_not_fail_the_scan():
    fake = FakeDiscovery(
        {"good": ["ok"], "bad": ["never seen"]},
        info_errors={"bad": KeyError("X_device")},
    )
    result, _ = run(fake)
    by_type = {d.device_type: d for d in result.discovered}
    assert by_type["good"].info == ["ok"]
    assert by_type["bad"].info == []
    assert "X_device" in (by_type["bad"].error or "")
    assert result.discovered_count == 1


def test_broken_mdns_cache_yields_empty_raw_zeroconf():
    fake = FakeDiscovery({"good": ["ok"]}, mdns_broken=True)
    result, _ = run(fake)
    assert result.zeroconf_entries == []
    assert result.discovered_count == 1


def test_empty_scan_is_a_result_not_an_error():
    result, _ = run(FakeDiscovery())
    assert result.discovered == []
    assert result.discovered_count == 0


def test_non_positive_seconds_rejected_before_scanning():
    fake = FakeDiscovery()
    for bad in (0, -1, -0.5):
        with pytest.raises(ValueError):
            run(fake, seconds=bad)
    assert not fake.scanned


def test_non_finite_and_over_limit_seconds_rejected():
    # NaN used to pass the old `seconds <= 0` check (both comparisons
    # are false for NaN) and then fail inside time.sleep(); inf did
    # the same in the other direction.
    fake = FakeDiscovery()
    for bad in (math.nan, math.inf, -math.inf, 3601):
        with pytest.raises(ValueError):
            run(fake, seconds=bad)
    assert not fake.scanned


def test_scan_config_object_path_and_no_descriptions():
    fake = FakeDiscovery({"good": ["ok"], "also": ["fine"]})
    calls = []
    original = fake.get_info

    def recording(device_type):
        calls.append(device_type)
        return original(device_type)

    fake.get_info = recording
    result, sleep_calls = run(
        fake,
        seconds=5.0,
    )
    assert result.seconds == 5.0
    result2 = scan_network(
        ScanConfig(seconds=2.5, include_descriptions=False),
        discovery_factory=lambda: fake,
        sleep=lambda value: sleep_calls.append(value),
    )
    assert result2.seconds == 2.5
    assert result2.descriptions_included is False
    assert [d.device_type for d in result2.discovered] == ["good", "also"]
    assert all(d.info == [] for d in result2.discovered)
    # get_info was called only for the first (descriptions-on) scan.
    assert calls == ["good", "also"]


def test_discover_non_iterable_raises_discovery_error():
    fake = FakeDiscovery({"good": ["ok"]})
    fake.discover = lambda: None  # type: ignore[method-assign]
    with pytest.raises(ScanError, match="did not return a list"):
        run(fake)
    assert fake.stopped


def test_adapter_delegates_to_inner_discovery():
    inner = FakeDiscovery({"good": ["ok"]}, zeroconf_entries=[FakeEntry("a")])
    adapter = NetdiscoDiscoveryAdapter(inner)
    adapter.scan()
    assert adapter.discover() == ["good"]
    assert adapter.get_info("good") == ["ok"]
    assert [repr(e) for e in adapter.mdns.entries] == ["<FakeEntry a>"]
    adapter.stop()
    assert inner.stopped


def test_stop_error_does_not_mask_a_good_result():
    fake = FakeDiscovery({"good": ["ok"]}, stop_error=True)
    result, _ = run(fake)
    assert result.discovered_count == 1
    assert fake.stopped


def test_to_jsonable_handles_mixed_and_unknown_values():
    when = datetime(2026, 1, 2, tzinfo=timezone.utc)
    assert to_jsonable({"b": b"hi", "when": when}) == {
        "b": "hi",
        "when": "2026-01-02T00:00:00+00:00",
    }
    assert to_jsonable({1, 2}) == [1, 2]
    assert to_jsonable(FakeEntry("x")) == "<FakeEntry x>"
    entry = FakeSsdpEntry({"location": "http://192.0.2.1/"})
    assert to_jsonable(entry) == {"location": "http://192.0.2.1/"}
    assert not entry.description_fetched
    assert to_jsonable([{"a": (1, 2)}]) == [{"a": [1, 2]}]


def test_to_jsonable_non_finite_floats_and_duplicate_keys(caplog):
    assert to_jsonable(math.nan) is None
    assert to_jsonable(math.inf) is None
    assert to_jsonable(-math.inf) is None
    assert to_jsonable({"a": 1.5}) == {"a": 1.5}
    caplog.set_level(logging.WARNING, logger="netdisco_scan.scanner")
    # Keys 1 and "1" stringify to the same key; the first wins, loudly.
    assert to_jsonable({1: "first", "1": "second"}) == {"1": "first"}
    assert "duplicate JSON key" in caplog.text


def test_default_factory_reports_missing_netdisco(monkeypatch):
    # A None entry makes the import raise ImportError, as if uninstalled.
    monkeypatch.setitem(sys.modules, "netdisco", None)
    monkeypatch.setitem(sys.modules, "netdisco.discovery", None)
    from netdisco_scan.scanner import _default_factory

    with pytest.raises(DependencyError, match="netdisco is not installed"):
        _default_factory()


def test_scan_result_counts_entries():
    result = ScanResult(seconds=1.0, discovered=[])
    assert result.discovered_count == 0
