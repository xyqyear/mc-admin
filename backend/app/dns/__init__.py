"""
DNS Management System

Simplified DNS management for Minecraft servers with direct Docker integration.
Supports DNSPod and Huawei Cloud DNS providers with on-demand updates.
"""

from .dns import DNSClient
from .dnspod import DNSPodClient
from .huawei import HuaweiDNSClient
from .manager import SimpleDNSManager, simple_dns_manager
from .router import MCRouterClient
from .types import (
    AddRecordListT,
    AddRecordT,
    RecordIdListT,
    RecordListT,
    ReturnRecordT,
)
from .utils import RecordDiff, RecordKey, diff_dns_records

__all__ = [
    "AddRecordListT",
    "AddRecordT",
    "DNSClient",
    "DNSPodClient",
    "HuaweiDNSClient",
    "MCRouterClient",
    "RecordDiff",
    "RecordIdListT",
    "RecordKey",
    "RecordListT",
    "ReturnRecordT",
    "SimpleDNSManager",
    "diff_dns_records",
    "simple_dns_manager",
]
