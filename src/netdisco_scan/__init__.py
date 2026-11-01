"""netdisco_scan: local-network device discovery (mDNS + SSDP)."""

from importlib.metadata import PackageNotFoundError, version

from .scanner import (
    DependencyError,
    DiscoveredDevice,
    Discovery,
    DiscoveryError,
    NetdiscoDiscoveryAdapter,
    ScanConfig,
    ScanError,
    ScanResult,
    scan_network,
    to_jsonable,
)

try:
    # Single source of truth for the version: pyproject.toml. The
    # fallback covers running from a source checkout without installing.
    __version__ = version("netdisco-scan")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

__all__ = [
    "DependencyError",
    "DiscoveredDevice",
    "Discovery",
    "DiscoveryError",
    "NetdiscoDiscoveryAdapter",
    "ScanConfig",
    "ScanError",
    "ScanResult",
    "__version__",
    "scan_network",
    "to_jsonable",
]
