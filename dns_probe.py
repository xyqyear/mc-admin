import asyncio
import collections
import datetime
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import dns.asyncquery
import dns.asyncresolver
import dns.flags
import dns.message
import dns.rcode
import dns.rdatatype
import dns.rrset
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkdns.v2 import (
    CreateRecordSetRequest,
    CreateRecordSetRequestBody,
    DeleteRecordSetsRequest,
    DnsClient,
    ListPublicZonesRequest,
    ListRecordSetsByZoneRequest,
)
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion


OUT = Path(os.environ.get("PROBE_OUT", "diagnostics"))
ALLOWED_ZONE = "e2e-test-mc.xyqyear.com"
OFFSETS = (0, 5, 10, 20, 30, 45, 60, 90, 120, 180, 300, 360)
DELAYS = (0, 30, 60)
SYSTEM_PROBE = os.environ.get("SYSTEM_PROBE", "./system-resolver-probe")
SCOPE_PATTERN = r"resolver-\d+-\d+-\d+-r\d+-d(?:0|30|60)"


def utc():
    return datetime.datetime.now(datetime.UTC).isoformat()


def save(name, value):
    OUT.mkdir(exist_ok=True, parents=True)
    target = OUT / name
    pending = target.with_suffix(target.suffix + ".tmp")
    pending.write_text(json.dumps(value, indent=2))
    pending.replace(target)


def event(name, value):
    OUT.mkdir(exist_ok=True, parents=True)
    with (OUT / name).open("a") as stream:
        stream.write(json.dumps(value) + "\n")


def safe_error(exc):
    return {"error_type": type(exc).__name__, "status": getattr(exc, "status_code", None), "error_code": getattr(exc, "error_code", None)}


class Cloud:
    def __init__(self):
        domain = os.environ["HUAWEICLOUD_DNS_ZONE"].lower().rstrip(".")
        if domain != ALLOWED_ZONE:
            raise ValueError("diagnostic writes restricted to the approved test zone")
        self.domain = domain
        http = HttpConfig.get_default_config()
        http.timeout = 20
        self.client = DnsClient.new_builder().with_credentials(
            BasicCredentials(os.environ["HUAWEICLOUD_AK"], os.environ["HUAWEICLOUD_SK"])
        ).with_region(DnsRegion.value_of(os.environ.get("HUAWEICLOUD_DNS_REGION") or "cn-north-4")).with_http_config(http).build()
        zones = self.client.list_public_zones(ListPublicZonesRequest(name=domain + ".", search_mode="equal", limit=500)).zones
        matching = [zone.id for zone in zones if zone.name == domain + "."]
        if len(matching) != 1:
            raise ValueError("test zone must match exactly")
        self.zone_id = matching[0]
        self.manifest = {"domain": domain, "zone_id": self.zone_id, "run_id": os.environ.get("GITHUB_RUN_ID"), "scopes": [], "cleaned": False}

    def records(self):
        result = []
        offset = 0
        while True:
            page = self.client.list_record_sets_by_zone(ListRecordSetsByZoneRequest(zone_id=self.zone_id, limit=500, offset=offset)).recordsets or []
            result.extend(page)
            if len(page) < 500:
                return result
            offset += len(page)

    def journal(self):
        save("ownership.json", self.manifest)

    def reserve(self, round_no, delay):
        scope = f"resolver-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}-{os.environ['PROBE_REPLICA']}-r{round_no}-d{delay}"
        if not re.fullmatch(SCOPE_PATTERN, scope):
            raise ValueError("invalid diagnostic ownership scope")
        base = f"primary.{scope}.{self.domain}."
        host = "vanilla." + base
        definitions = [
            {"name": "*." + base, "type": "A", "values": ["127.0.0.1"]},
            {"name": "_minecraft._tcp." + host, "type": "SRV", "values": ["0 5 25565 " + host]},
            {"name": "exact." + base, "type": "A", "values": ["127.0.0.1"]},
        ]
        entry = {"scope": scope, "round": round_no, "initial_delay": delay, "definitions": definitions, "created": []}
        self.manifest["scopes"].append(entry)
        self.journal()
        return entry

    def create(self, entry):
        allowed = {d["name"] for d in entry["definitions"]}
        if any(record.name in allowed for record in self.records()):
            raise ValueError("diagnostic scope already contains records")
        for definition in entry["definitions"]:
            started = time.monotonic()
            response = self.client.create_record_set(CreateRecordSetRequest(zone_id=self.zone_id, body=CreateRecordSetRequestBody(
                name=definition["name"], type=definition["type"], ttl=600, records=definition["values"], description="Temporary mc-admin default resolver comparison"
            )))
            entry["created"].append({"name": definition["name"], "type": definition["type"], "id": response.id, "status": response.status, "utc": utc(), "api_seconds": time.monotonic() - started})
            self.journal()
        epoch = time.monotonic()
        entry["epoch_utc"] = utc()
        self.journal()
        return epoch

    def verify(self, entry):
        wanted = {(d["name"], d["type"]): sorted(d["values"]) for d in entry["definitions"]}
        actual = {(r.name, r.type): sorted(r.records) for r in self.records() if (r.name, r.type) in wanted}
        if actual != wanted:
            raise ValueError("provider API records differ from owned plan")
        event("api-checks.jsonl", {"scope": entry["scope"], "utc": utc(), "verified": True})

    def cleanup(self):
        path = OUT / "ownership.json"
        if not path.exists():
            save("cleanup.json", {"cleaned": True, "reason": "no cloud mutation journal"})
            return
        manifest = json.loads(path.read_text())
        if manifest["domain"] != self.domain or manifest["zone_id"] != self.zone_id or manifest["run_id"] != os.environ["GITHUB_RUN_ID"]:
            raise ValueError("cleanup identity mismatch")
        allowed = {}
        for entry in manifest["scopes"]:
            expected_prefix = f"resolver-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}-{os.environ['PROBE_REPLICA']}-"
            if not entry["scope"].startswith(expected_prefix) or not re.fullmatch(SCOPE_PATTERN, entry["scope"]):
                raise ValueError("invalid cleanup scope")
            for definition in entry["definitions"]:
                if not definition["name"].endswith("." + entry["scope"] + "." + self.domain + "."):
                    raise ValueError("cleanup target outside owned scope")
                allowed[(definition["name"], definition["type"])] = sorted(definition["values"])
        failures = []
        for record in self.records():
            key = (record.name, record.type)
            if key not in allowed:
                continue
            if sorted(record.records) != allowed[key]:
                failures.append({"name": record.name, "reason": "ownership value mismatch"})
                continue
            try:
                self.client.delete_record_sets(DeleteRecordSetsRequest(zone_id=self.zone_id, recordset_id=record.id))
            except Exception as exc:
                failures.append({"name": record.name, **safe_error(exc)})
        remaining = []
        for attempt in range(15):
            remaining = [r.name for r in self.records() if (r.name, r.type) in allowed]
            if not remaining:
                break
            time.sleep(2)
        clean = not remaining and not failures
        manifest["cleaned"] = clean
        save("ownership.json", manifest)
        save("cleanup.json", {"cleaned": clean, "remaining": remaining, "errors": failures, "created_record_count": sum(len(entry["created"]) for entry in manifest["scopes"]), "planned_record_count": len(allowed), "utc": utc()})
        if not clean:
            raise ValueError("owned DNS cleanup incomplete")


async def discover():
    resolver = dns.asyncresolver.Resolver()
    records = await resolver.resolve(ALLOWED_ZONE, "NS", lifetime=10)
    mapping = {}
    for record in records:
        name = record.target.to_text()
        if "huaweicloud-dns." not in name:
            raise ValueError("test zone delegates to unexpected nameserver")
        values = await resolver.resolve(name, "A", lifetime=10)
        mapping[name] = sorted({value.address for value in values})
    current = sorted({ip for ips in mapping.values() for ip in ips})
    return mapping, current


def query_message(name, rrtype, authoritative):
    return dns.message.make_query(name, rrtype, flags=0 if authoritative else dns.flags.RD, use_edns=False)


def response_data(response, query, expected, authoritative):
    answers = [r.to_text() for rrset in response.answer if rrset.name == query.question[0].name and rrset.rdtype == query.question[0].rdtype for r in rrset]
    negative_ttls = [min(rrset.ttl, r.minimum) for rrset in response.authority if rrset.rdtype == dns.rdatatype.SOA for r in rrset]
    return {
        "rcode": dns.rcode.to_text(response.rcode()),
        "aa": bool(response.flags & dns.flags.AA),
        "ra": bool(response.flags & dns.flags.RA),
        "answers": answers,
        "answer": [rrset.to_text() for rrset in response.answer],
        "authority": [rrset.to_text() for rrset in response.authority],
        "negative_ttl_seconds": min(negative_ttls, default=None),
        "ok": response.rcode() == dns.rcode.NOERROR and (not authoritative or bool(response.flags & dns.flags.AA)) and not bool(response.flags & dns.flags.TC) and (answers == [expected] if expected is not None else bool(answers)),
    }


async def wire_sample(row, name, rrtype, expected, target, transport, authoritative):
    try:
        query = query_message(name, rrtype, authoritative)
        response = await getattr(dns.asyncquery, transport)(query, target, timeout=3)
        row.update(response_data(response, query, expected, authoritative))
    except Exception as exc:
        row.update({"ok": False, **safe_error(exc)})


async def system_sample(row, name, rrtype, expected):
    process = await asyncio.create_subprocess_exec(SYSTEM_PROBE, name, rrtype, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=6)
    except TimeoutError:
        process.kill()
        await process.communicate()
        row.update({"ok": False, "error_type": "ProbeProcessTimeout"})
        return
    if process.returncode != 0:
        raise ValueError("system resolver instrumentation failed")
    result = json.loads(stdout)
    row.update(result)
    row["ok"] = not result.get("error_type") and (result["answers"] == [expected] if expected is not None else bool(result["answers"]))


async def baseline(ips, resolver_ips):
    async def sample(method, target, transport):
        name, kind = (ALLOWED_ZONE + ".", "SOA") if method == "authoritative" else ("github.com.", "A")
        row = {"method": method, "ip": target, "transport": transport, "name": name, "type": kind, "utc": utc()}
        started = time.monotonic()
        if method == "system_go":
            await system_sample(row, name, kind, None)
        else:
            await wire_sample(row, name, kind, None, target, transport, method == "authoritative")
        row["duration_seconds"] = round(time.monotonic() - started, 4)
        event("baseline.jsonl", row)

    await asyncio.gather(
        *(sample(method, target, transport) for method, targets in (("authoritative", ips), ("recursive", resolver_ips)) for target in targets for transport in ("udp", "tcp")),
        sample("system_go", "net.DefaultResolver", "default"),
    )


async def measure(entry, epoch, ips, resolver_ips, global_limit, limits):
    base = f"primary.{entry['scope']}.{ALLOWED_ZONE}."
    host = "vanilla." + base
    checks = {
        "server_a": (host, "A", "127.0.0.1"),
        "srv": ("_minecraft._tcp." + host, "SRV", "0 5 25565 " + host),
        "wildcard_control": ("random." + base, "A", "127.0.0.1"),
        "exact_control": ("exact." + base, "A", "127.0.0.1"),
    }
    async def sample(offset, method, ip, transport, kind):
        await asyncio.sleep(max(0, epoch + offset - time.monotonic()))
        async with global_limit, limits[ip]:
            name, rrtype, expected = checks[kind]
            started = time.monotonic()
            row = {"scope": entry["scope"], "round": entry["round"], "initial_delay": entry["initial_delay"], "scheduled_seconds": offset, "started_seconds": round(started - epoch, 4), "utc": utc(), "method": method, "ip": ip, "transport": transport, "kind": kind, "name": name, "type": rrtype}
            if method == "system_go":
                await system_sample(row, name, rrtype, expected)
            else:
                await wire_sample(row, name, rrtype, expected, ip, transport, method == "authoritative")
            row["duration_seconds"] = round(time.monotonic() - started, 4)
            row["finished_seconds"] = round(time.monotonic() - epoch, 4)
            event("queries.jsonl", row)
    tasks = []
    for offset in OFFSETS:
        if offset < entry["initial_delay"]:
            continue
        for method, targets in (("authoritative", ips), ("recursive", resolver_ips)):
            for ip in targets:
                for transport in ("udp", "tcp"):
                    for kind in checks:
                        tasks.append(asyncio.create_task(sample(offset, method, ip, transport, kind)))
        for kind in checks:
            tasks.append(asyncio.create_task(sample(offset, "system_go", "net.DefaultResolver", "default", kind)))
    await asyncio.gather(*tasks)


def summarize():
    rows = [json.loads(line) for line in (OUT / "queries.jsonl").read_text().splitlines()]
    counts = collections.Counter((row["method"], row["transport"], row["initial_delay"], row.get("rcode", row.get("error_type", "success")), row["ok"]) for row in rows)
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["scope"], row["method"], row["ip"], row["transport"], row["kind"])].append(row)
    series = []
    for key, values in sorted(grouped.items()):
        values.sort(key=lambda r: r["started_seconds"])
        first = next((r["finished_seconds"] for r in values if r["ok"]), None)
        failures = [r for r in values if not r["ok"]]
        last_failed = max((r["started_seconds"] for r in failures), default=None)
        tail = next((r["finished_seconds"] for r in values if r["ok"] and (last_failed is None or r["started_seconds"] > last_failed)), None)
        series.append({"scope": key[0], "method": key[1], "ip": key[2], "transport": key[3], "kind": key[4], "first_success_seconds": first, "successful_tail_seconds": tail, "failures": len(failures), "total": len(values), "last_ok": values[-1]["ok"]})
    save("summary.json", {"query_count": len(rows), "counts": [{"method": k[0], "transport": k[1], "initial_delay": k[2], "result": k[3], "ok": k[4], "count": v} for k, v in sorted(counts.items())], "series": series})


async def run():
    resolver = dns.asyncresolver.Resolver()
    mapping, ips = await discover()
    resolver_ips = [str(ip) for ip in resolver.nameservers]
    metadata = {"utc": utc(), "zone": ALLOWED_ZONE, "nameservers": mapping, "ips": ips, "system_nameservers": resolver_ips, "revision": os.environ.get("GITHUB_SHA"), "replica": os.environ.get("PROBE_REPLICA"), "query_timeout_seconds": 3, "ttl": 600, "offsets": OFFSETS, "initial_delays": DELAYS, "system_probe": json.loads(subprocess.check_output([SYSTEM_PROBE, "--version"]))}
    for filename in ("/etc/resolv.conf", "/run/systemd/resolve/resolv.conf", "/run/systemd/resolve/stub-resolv.conf"):
        path = Path(filename)
        if path.exists():
            metadata[filename] = path.read_text()
    try:
        request = urllib.request.Request("http://169.254.169.254/metadata/instance/compute?api-version=2021-02-01", headers={"Metadata": "true"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            metadata["azure_location"] = json.load(response).get("location")
    except Exception as exc:
        metadata["metadata_error"] = type(exc).__name__
    save("metadata.json", metadata)
    print(json.dumps(metadata), flush=True)
    await baseline(ips, resolver_ips)
    cloud = await asyncio.to_thread(Cloud)
    global_limit = asyncio.Semaphore(64)
    limits = {ip: asyncio.Semaphore(8) for ip in ips + resolver_ips + ["net.DefaultResolver"]}
    try:
        for round_no in range(1, 2):
            async with asyncio.TaskGroup() as group:
                for delay in DELAYS:
                    entry = cloud.reserve(round_no, delay)
                    epoch = await asyncio.to_thread(cloud.create, entry)
                    group.create_task(measure(entry, epoch, ips, resolver_ips, global_limit, limits))
                    await asyncio.to_thread(cloud.verify, entry)
                print(json.dumps({"round": round_no, "state": "sampling", "utc": utc()}), flush=True)
            print(json.dumps({"round": round_no, "state": "complete", "utc": utc()}), flush=True)
        summarize()
    finally:
        await asyncio.to_thread(cloud.cleanup)


def validate():
    assert list(OFFSETS) == sorted(set(OFFSETS))
    for delay in DELAYS:
        assert delay in (0, 30, 60)
        assert delay in OFFSETS
    message = query_message("vanilla.primary.example.test.", "A", True)
    assert message.flags == 0 and message.edns == -1
    message = query_message("vanilla.primary.example.test.", "A", False)
    assert message.flags == dns.flags.RD and message.edns == -1
    response = dns.message.make_response(message)
    response.answer.append(dns.rrset.from_text("vanilla.primary.example.test.", 600, "IN", "A", "127.0.0.1"))
    assert response_data(response, message, "127.0.0.1", False)["ok"]
    assert not response_data(response, message, "127.0.0.1", True)["ok"]
    response.answer.clear()
    response.set_rcode(dns.rcode.NXDOMAIN)
    response.authority.append(dns.rrset.from_text("example.test.", 300, "IN", "SOA", "ns.example.test. hostmaster.example.test. 1 60 60 600 900"))
    result = response_data(response, message, "127.0.0.1", False)
    assert not result["ok"] and result["negative_ttl_seconds"] == 300
    assert "credential" not in json.dumps(safe_error(ValueError("credential")))
    print("diagnostic schedule, DNS flags, response assertions and redaction validated; no cloud access")


if __name__ == "__main__":
    try:
        mode = sys.argv[1] if len(sys.argv) > 1 else "run"
        if mode == "validate":
            validate()
        elif mode == "cleanup":
            Cloud().cleanup()
        elif mode == "run":
            asyncio.run(run())
        else:
            raise ValueError("unknown diagnostic mode")
    except Exception as exc:
        value = {"utc": utc(), **safe_error(exc)}
        save("fatal.json", value)
        print(json.dumps(value), flush=True)
        sys.exit(1)
