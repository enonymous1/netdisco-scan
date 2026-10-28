"""Scan the local network for devices and services (mDNS + SSDP)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class ScanError(Exception):
    """Raised when a scan cannot start or complete."""


@dataclass
class DiscoveredDevice:
    """One device type recognised by netdisco, with its info entries."""

    device_type: str
    info: list[Any] = field(default_factory=list)
    error: str | None = None


@dataclass
class ScanResult:
    """Everything one scan found, captured before discovery is stopped."""

    seconds: float
    discovered: list[DiscoveredDevice] = field(default_factory=list)
    zeroconf_entries: list[Any] = field(default_factory=list)
    ssdp_entries: list[Any] = field(default_factory=list)

    @property
    def discovered_count(self) -> int:
        """Total info entries across all discovered device types."""
        return sum(len(device.info) for device in self.discovered)


def to_jsonable(value: Any, _depth: int = 0) -> Any:
    """Convert arbitrary scan data into JSON-serialisable values.

    Unknown objects become their ``str()`` form, bytes are decoded,
    datetimes become ISO strings, and SSDP entries contribute only
    their header ``values`` dict -- never their fetched description,
    so serialising a result performs no network access.
    """
    if _depth > 20:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): to_jsonable(item, _depth + 1) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item, _depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(item, _depth + 1) for item in sorted(value, key=repr)]
    values = getattr(value, "values", None)
    if isinstance(values, dict):
        return to_jsonable(values, _depth + 1)
    return str(value)


def _default_factory() -> Any:
    """Create a real ``NetworkDiscovery``. Imported lazily so ``--help``
    and the test suite work without netdisco installed."""
    try:
        from netdisco.discovery import NetworkDiscovery
    except ImportError as exc:  # pragma: no cover - exercised in CI with netdisco
        raise ScanError(
            "netdisco is not installed. Install this package with its "
            "dependencies (pip install .) or: pip install netdisco==3.0.0"
        ) from exc
    return NetworkDiscovery()


def _raw_zeroconf(discovery: Any) -> list[Any]:
    """Capture mDNS cache entries, defensively: the cache property can
    raise if discovery never started its Zeroconf instance."""
    try:
        mdns = getattr(discovery, "mdns", None)
        if mdns is None:
            return []
        return list(mdns.entries)
    except Exception:
        return []


def _raw_ssdp(discovery: Any) -> list[Any]:
    """Capture SSDP entries (header values only; no description fetch)."""
    try:
        ssdp = getattr(discovery, "ssdp", None)
        if ssdp is None:
            return []
        return list(ssdp.entries)
    except Exception:
        return []


def _collect(discovery: Any, seconds: float) -> ScanResult:
    """Read everything from a running discovery, before it is stopped.

    Raw entries are captured first: ``stop()`` clears the mDNS side, so
    reading them afterwards would lose the Zeroconf cache. Each device
    type's ``get_info()`` is isolated -- one type that raises (for
    example a malformed device description) is recorded as an error
    instead of failing the whole scan. ``get_info()`` itself may fetch
    a device description over HTTP; that is upstream netdisco behaviour.
    """
    zeroconf_entries = _raw_zeroconf(discovery)
    ssdp_entries = _raw_ssdp(discovery)
    try:
        device_types = discovery.discover()
    except Exception as exc:
        raise ScanError(f"discovery failed: {exc}") from exc
    discovered: list[DiscoveredDevice] = []
    for device_type in device_types:
        try:
            info = discovery.get_info(device_type)
        except Exception as exc:
            discovered.append(DiscoveredDevice(device_type, [], error=str(exc)))
            continue
        if not isinstance(info, list):
            info = [info]
        discovered.append(DiscoveredDevice(device_type, info))
    return ScanResult(
        seconds=seconds,
        discovered=discovered,
        zeroconf_entries=zeroconf_entries,
        ssdp_entries=ssdp_entries,
    )


def scan_network(
    seconds: float,
    *,
    discovery_factory: Any = None,
    sleep: Any = None,
) -> ScanResult:
    """Run one scan for ``seconds`` and return its result.

    ``discovery_factory`` and ``sleep`` are injectable so tests can run
    without touching the network. Discovery is always stopped, even
    when the wait is interrupted or collection fails.
    """
    if seconds <= 0:
        raise ValueError("seconds must be greater than 0")
    if sleep is None:
        import time

        sleep = time.sleep
    discovery = (discovery_factory or _default_factory)()
    try:
        discovery.scan()
        sleep(seconds)
        return _collect(discovery, seconds)
    finally:
        try:
            discovery.stop()
        except Exception:
            pass
