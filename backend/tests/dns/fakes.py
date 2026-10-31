import asyncio

from app.dns.dns import DNSClient
from app.dns.router import MCRouterClient
from app.dns.types import ReturnRecordT


class StatefulDNS(DNSClient):
    def __init__(self, domain="example.com"):
        self.domain = domain
        self.records = []
        self.calls = []
        self.unavailable = False
        self.fail_name = None
        self.next_id = 1
        self.started: asyncio.Event | None = None
        self.release: asyncio.Event | None = None
        self.closed = False
        self.initialized = True
        self.initialization_error: Exception | None = None

    def get_domain(self):
        return self.domain

    def is_initialized(self):
        return self.initialized

    async def init(self):
        if self.initialization_error is not None:
            raise self.initialization_error
        self.initialized = True

    async def list_records(self):
        if self.unavailable:
            raise OSError("synthetic-provider-secret")
        return list(self.records)

    async def add_records(self, records):
        for record in records:
            self.calls.append(("add", record.sub_domain))
            if self.started is not None:
                self.started.set()
                assert self.release is not None
                await self.release.wait()
            if record.sub_domain == self.fail_name:
                raise OSError("synthetic-provider-secret")
            self.records.append(ReturnRecordT(record.sub_domain, record.value, self.next_id, record.record_type, record.ttl))
            self.next_id += 1

    async def remove_records(self, record_ids):
        self.calls.extend(("remove", identifier) for identifier in record_ids)
        self.records = [record for record in self.records if record.record_id not in record_ids]

    def has_update_capability(self):
        return True

    async def _update_records_batch(self, records):
        for record in records:
            self.calls.append(("update", record.sub_domain))
            self.records = [record if current.record_id == record.record_id else current for current in self.records]

    async def close(self):
        self.closed = True


class StatefulRouter(MCRouterClient):
    def __init__(self):
        self.routes = {}
        self.calls = []
        self.unavailable = False
        self.fail_name = None
        self.closed = False

    async def _send_request(self, method, path, headers=None, json=None):
        if method == "GET":
            if self.unavailable:
                raise OSError("synthetic-router-secret")
            return {key: {"backend": value} for key, value in self.routes.items()}
        self.calls.append((method, path, json))
        if method == "POST":
            assert json is not None
            if json["serverAddress"] == self.fail_name:
                raise OSError("synthetic-router-secret")
            self.routes[json["serverAddress"]] = json["backend"]
        elif method == "DELETE":
            self.routes.pop(path.removeprefix("routes/"), None)
        return None

    async def close(self):
        self.closed = True


