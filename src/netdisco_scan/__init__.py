"""netdisco_scan: local-network device discovery (mDNS + SSDP)."""

from .scanner import ScanError, ScanResult, scan_network

__version__ = "2.0.0"
__all__ = ["ScanError", "ScanResult", "__version__", "scan_network"]
