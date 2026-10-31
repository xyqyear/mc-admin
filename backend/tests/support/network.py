import ipaddress
import socket
from typing import Any

import pytest


def require_local_address(host: Any) -> None:
    if host is None:
        return
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (address.is_loopback or (
        isinstance(address, ipaddress.IPv6Address)
        and address.ipv4_mapped is not None and address.ipv4_mapped.is_loopback
    )):
        return
    raise RuntimeError("External network requires @pytest.mark.external and --run-external")


def guard_network(monkeypatch: pytest.MonkeyPatch) -> None:
    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, *args, **kwargs):
        require_local_address(host)
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)

    for name in ("connect", "connect_ex", "sendto"):
        original = getattr(socket.socket, name)

        def guarded(sock, *args, _original=original, **kwargs):
            if sock.family in (socket.AF_INET, socket.AF_INET6):
                address = args[-1]
                require_local_address(address[0])
            return _original(sock, *args, **kwargs)

        monkeypatch.setattr(socket.socket, name, guarded)
