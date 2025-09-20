"""
DNS Management System

Integrated DNS management for Minecraft servers with Docker integration.
Supports DNSPod and Huawei Cloud DNS providers with automatic server discovery and routing.
"""

from .dns import (
    AddRecordListT,
    AddRecordT,
    DNSClient,
    RecordIdListT,
    RecordListT,
    ReturnRecordT,
)
from .dnspod import DNSPodClient
from .huawei import HuaweiDNSClient
from .manager import DNSManager, dns_manager
from .mcdns import MCDNS, AddressesT, AddressInfoT, MCDNSPullResultT

__all__ = [
    "DNSClient",
    "AddRecordT",
    "ReturnRecordT",
    "RecordListT",
    "AddRecordListT",
    "RecordIdListT",
    "DNSPodClient",
    "HuaweiDNSClient",
    "MCDNS",
    "AddressesT",
    "AddressInfoT",
    "MCDNSPullResultT",
    "DNSManager",
    "dns_manager",
]
