"""Scan the local network for devices and services (mDNS + SSDP)."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Maximum listen window. This is an operational cap against typos (an
# hour-long listen is almost certainly a mistake), not a protocol
# limit: netdisco itself imposes no such bound. The CLI and the library
# API share this constant so they cannot drift apart again.
MAX_SCAN_SECONDS = 3600

# Maximum nesting depth converted by to_jsonable. Scan data is shallow
# in practice; the cap exists so a cyclic structure degrades to its
# str() form instead of recursing forever.
_MAX_JSON_DEPTH = 20


class ScanError(Exception):
    """Base class for scan failures."""


class DependencyError(ScanError):
    """Raised when the netdisco dependency is missing."""


class DiscoveryError(ScanError):
    """Raised when a running discovery fails to report its devices."""


@dataclass
class DiscoveredDevice:
    """One device type recognised by netdisco, with its info entries.

    ``error`` is a plain string, not the original exception, because
    results are meant to be printed and serialised: the exception type
    is lost when converted, so callers that need it should record it
    before constructing this object.
    """

    device_type: str
    info: list[Any] = field(default_factory=list)
    error: str | None = None


@dataclass
class ScanResult:
    """Everything one scan found, captured before discovery is stopped.

    The raw entry lists hold the upstream objects themselves (Zeroconf
    records, SSDP entries), not JSON values: convert them with
    :func:`to_jsonable` at the rendering boundary, never earlier, so
    serialising a result performs no network access.
    """

    seconds: float
    discovered: list[DiscoveredDevice] = field(default_factory=list)
    zeroconf_entries: list[Any] = field(default_factory=list)
    ssdp_entries: list[Any] = field(default_factory=list)
    descriptions_included: bool = True

    @property
    def discovered_count(self) -> int:
        """Total info entries across all discovered device types.

        This counts entries, not physical devices: one type with three
        info entries counts as three. Renderers must say so.
        """
        return sum(len(device.info) for device in self.discovered)


@runtime_checkable
class Discovery(Protocol):
    """Contract a discovery backend must satisfy.

    This is deliberately the smallest surface ``scan_network`` needs:
    a future backend (for example, a zeroconf-native one replacing the
    deprecated netdisco library) implements this protocol instead of
    mimicking netdisco's internals. ``mdns`` and ``ssdp`` are read-only
    properties exposing the raw entry sources; backends that have no
    equivalent expose empty lists there.
    """

    @property
    def mdns(self) -> Any:
        """Raw mDNS source (an object with an ``entries`` attribute)."""
        ...

    @property
    def ssdp(self) -> Any:
        """Raw SSDP source (an object with an ``entries`` attribute)."""
        ...

    def scan(self) -> None:
        """Start discovery."""
        ...

    def discover(self) -> list[str]:
        """Return the recognised device-type names."""
        ...

    def get_info(self, device_type: str) -> list[Any]:
        """Return the info entries for one device type."""
        ...

    def stop(self) -> None:
        """Stop discovery and release its resources."""
        ...


class NetdiscoDiscoveryAdapter:
    """Adapts netdisco's ``NetworkDiscovery`` to :class:`Discovery`.

    All netdisco-specific attribute access (``.mdns`` / ``.ssdp``)
    lives in this class's properties. Replacing the backend means
    replacing this class, not ``scan_network`` or ``_collect``.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner

    @property
    def mdns(self) -> Any:
        return getattr(self._inner, "mdns", None)

    @property
    def ssdp(self) -> Any:
        return getattr(self._inner, "ssdp", None)

    def scan(self) -> None:
        self._inner.scan()

    def discover(self) -> list[str]:
        # Coerce here so callers never see a generator or other
        # one-shot iterable from the backend.
        return list(self._inner.discover())

    def get_info(self, device_type: str) -> list[Any]:
        return self._inner.get_info(device_type)

    def stop(self) -> None:
        self._inner.stop()


@dataclass(frozen=True)
class ScanConfig:
    """Options for one scan.

    ``seconds`` is the listen window, not a total time budget (see
    :func:`scan_network`). ``include_descriptions`` controls only the
    ``get_info()`` calls: when false, device types are still listed
    but no info is fetched for them. Note the upstream caveat that
    ``discover()`` itself may fetch SSDP descriptions while matching
    device types, so disabling descriptions reduces, but does not
    eliminate, description traffic.
    """

    seconds: float = 5.0
    include_descriptions: bool = True


def to_jsonable(value: Any, _depth: int = 0) -> Any:
    """Convert arbitrary scan data into JSON-serialisable values.

    Unknown objects become their ``str()`` form, bytes are decoded,
    datetimes become ISO strings, and non-finite floats become
    ``None`` (JSON has no NaN/Infinity literals, so passing them
    through would produce invalid strict JSON). SSDP entries
    contribute only their header ``values`` dict when that attribute
    is a dict -- never their fetched description, so serialising a
    result performs no network access. Dict keys are stringified;
    when two keys stringify to the same string, the first value is
    kept and a warning is logged rather than silently overwriting it.
    """
    if _depth > _MAX_JSON_DEPTH:
        return str(value)
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            str_key = str(key)
            if str_key in result:
                logger.warning("duplicate JSON key %r; keeping first value", str_key)
                continue
            result[str_key] = to_jsonable(item, _depth + 1)
        return result
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item, _depth + 1) for item in value]
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(item, _depth + 1) for item in sorted(value, key=repr)]
    values = getattr(value, "values", None)
    if isinstance(values, dict):
        return to_jsonable(values, _depth + 1)
    return str(value)


def _default_factory() -> Discovery:
    """Create a real discovery backend. Imported lazily so ``--help``
    and the test suite work without netdisco installed."""
    try:
        from netdisco.discovery import NetworkDiscovery
    except ImportError as exc:
        raise DependencyError(
            "netdisco is not installed. Install this package with its "
            "dependencies (pip install .) or: pip install netdisco==3.0.0"
        ) from exc
    return NetdiscoDiscoveryAdapter(NetworkDiscovery())


def _raw_zeroconf(discovery: Discovery) -> list[Any]:
    """Capture mDNS cache entries, defensively: the cache property can
    raise if discovery never started its Zeroconf instance. A failure
    is logged and yields an empty list, because an empty raw section
    is recoverable while a failed scan is not."""
    try:
        mdns = discovery.mdns
        if mdns is None:
            return []
        return list(mdns.entries)
    except Exception as exc:
        logger.warning("could not read mDNS cache: %s", exc)
        return []


def _raw_ssdp(discovery: Discovery) -> list[Any]:
    """Capture SSDP entries (header values only; no description fetch)."""
    try:
        ssdp = discovery.ssdp
        if ssdp is None:
            return []
        return list(ssdp.entries)
    except Exception as exc:
        logger.warning("could not read SSDP entries: %s", exc)
        return []


def _collect(
    discovery: Discovery,
    seconds: float,
    include_descriptions: bool = True,
) -> ScanResult:
    """Read everything from a running discovery, before it is stopped.

    Raw entries are captured first: ``stop()`` clears the mDNS side, so
    reading them afterwards would lose the Zeroconf cache. Each device
    type's ``get_info()`` is isolated -- one type that raises (for
    example a malformed device description) is recorded as an error
    instead of failing the whole scan. ``get_info()`` itself may fetch
    a device description over HTTP; that is upstream netdisco behaviour.
    When ``include_descriptions`` is false, ``get_info()`` is skipped
    entirely and types are listed with empty info.
    """
    zeroconf_entries = _raw_zeroconf(discovery)
    ssdp_entries = _raw_ssdp(discovery)
    try:
        device_types = discovery.discover()
    except Exception as exc:
        raise DiscoveryError(f"discovery failed: {exc}") from exc
    if isinstance(device_types, str) or not isinstance(device_types, Iterable):
        raise DiscoveryError("discover() did not return a list of device types")
    device_types = list(device_types)
    discovered: list[DiscoveredDevice] = []
    for device_type in device_types:
        if not include_descriptions:
            discovered.append(DiscoveredDevice(device_type, []))
            continue
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
        descriptions_included=include_descriptions,
    )


def scan_network(
    config_or_seconds: float | ScanConfig = 5.0,
    *,
    discovery_factory: Callable[[], Discovery] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> ScanResult:
    """Run one scan and return its result.

    ``config_or_seconds`` accepts either a :class:`ScanConfig` or a
    plain number of seconds (kept for the v2.0.0 call shape). ``seconds``
    is the listen window, not a total time budget: after it elapses,
    ``get_info()`` may still fetch device descriptions over HTTP (one
    per recognised type, sequentially), so wall time can exceed it.
    Raises ``ValueError`` for non-finite, non-positive, or over-limit
    seconds. ``discovery_factory`` and ``sleep`` are injectable so
    tests can run without touching the network. Discovery is always
    stopped, even when the wait is interrupted or collection fails; a
    failure to stop is logged, not raised, so it cannot mask the
    result or the original error.
    """
    if isinstance(config_or_seconds, ScanConfig):
        config = config_or_seconds
    else:
        config = ScanConfig(seconds=float(config_or_seconds))
    seconds = config.seconds
    if not math.isfinite(seconds) or seconds <= 0 or seconds > MAX_SCAN_SECONDS:
        raise ValueError(f"seconds must be finite and in (0, {MAX_SCAN_SECONDS}]")
    if sleep is None:
        sleep = time.sleep
    discovery = (discovery_factory or _default_factory)()
    try:
        discovery.scan()
        sleep(seconds)
        return _collect(
            discovery,
            seconds,
            include_descriptions=config.include_descriptions,
        )
    finally:
        try:
            discovery.stop()
        except Exception as exc:
            logger.warning("discovery stop failed (ignored): %s", exc)
