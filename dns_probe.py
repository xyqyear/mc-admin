import asyncio
import collections
import datetime
import json
import os
import re
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
OFFSETS = tuple(json.loads(os.environ.get("PROBE_OFFSETS", "[0,2,5,10,15,20,30,45,60,90,120,180]")))
DELAYS = tuple(json.loads(os.environ.get("PROBE_DELAYS", "[0,5,10]")))


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
        scope = f"delay-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}-{os.environ['PROBE_REPLICA']}-r{round_no}-d{delay}"
        if not re.fullmatch(r"delay-\d+-\d+-\d+-r\d+-d(?:0|5|10|30)", scope):
            raise ValueError("invalid diagnostic ownership scope")
        base = f"primary.{scope}.{self.domain}."
        host = "vanilla." + base
        definitions = [
            {"name": "*." + base, "type": "A", "values": ["192.0.2.10"]},
            {"name": "_minecraft._tcp." + host, "type": "SRV", "values": ["0 5 25565 " + host]},
            {"name": "exact." + base, "type": "A", "values": ["192.0.2.20"]},
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
                name=definition["name"], type=definition["type"], ttl=600, records=definition["values"], description="Temporary mc-admin DNS propagation measurement"
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
            expected_prefix = f"delay-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}-{os.environ['PROBE_REPLICA']}-"
            if not entry["scope"].startswith(expected_prefix) or not re.fullmatch(r"delay-\d+-\d+-\d+-r\d+-d(?:0|5|10|30)", entry["scope"]):
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
        save("cleanup.json", {"cleaned": clean, "remaining": remaining, "errors": failures, "utc": utc()})
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
    historical = ["114.115.192.11", "190.92.196.2", "122.112.208.254"]
    return mapping, sorted(set(current + historical)), current


async def measure(entry, epoch, ips, global_limit, limits):
    base = f"primary.{entry['scope']}.{ALLOWED_ZONE}."
    host = "vanilla." + base
    checks = {
        "server_a": (host, "A", "192.0.2.10"),
        "srv": ("_minecraft._tcp." + host, "SRV", "0 5 25565 " + host),
        "wildcard_control": ("random." + base, "A", "192.0.2.10"),
        "exact_control": ("exact." + base, "A", "192.0.2.20"),
    }
    async def sample(offset, ip, transport, kind):
        await asyncio.sleep(max(0, epoch + offset - time.monotonic()))
        async with global_limit, limits[ip]:
            name, rrtype, expected = checks[kind]
            started = time.monotonic()
            row = {"scope": entry["scope"], "round": entry["round"], "initial_delay": entry["initial_delay"], "scheduled_seconds": offset, "started_seconds": round(started - epoch, 4), "utc": utc(), "ip": ip, "transport": transport, "kind": kind, "name": name, "type": rrtype}
            try:
                query = dns.message.make_query(name, rrtype, flags=0, use_edns=False)
                response = await getattr(dns.asyncquery, transport)(query, ip, timeout=3)
                answers = [r.to_text() for rrset in response.answer if rrset.name == query.question[0].name and rrset.rdtype == query.question[0].rdtype for r in rrset]
                row.update({"rcode": dns.rcode.to_text(response.rcode()), "aa": bool(response.flags & dns.flags.AA), "answers": answers, "answer": [rrset.to_text() for rrset in response.answer], "authority": [rrset.to_text() for rrset in response.authority]})
                row["ok"] = response.rcode() == dns.rcode.NOERROR and row["aa"] and not response.flags & dns.flags.TC and answers == [expected]
            except Exception as exc:
                row.update({"ok": False, **safe_error(exc)})
            row["finished_seconds"] = round(time.monotonic() - epoch, 4)
            event("queries.jsonl", row)
    tasks = []
    for offset in OFFSETS:
        if offset < entry["initial_delay"]:
            continue
        kinds = checks if offset in {entry["initial_delay"], 5, 10, 30, 60, 120, 180} else {"server_a": checks["server_a"]}
        for ip in ips:
            for transport in ("udp", "tcp"):
                for kind in kinds:
                    tasks.append(asyncio.create_task(sample(offset, ip, transport, kind)))
    await asyncio.gather(*tasks)


def summarize():
    rows = [json.loads(line) for line in (OUT / "queries.jsonl").read_text().splitlines()]
    counts = collections.Counter((row["transport"], row.get("rcode", row.get("error_type")), row["ok"]) for row in rows)
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["scope"], row["ip"], row["transport"], row["kind"])].append(row)
    series = []
    for key, values in sorted(grouped.items()):
        values.sort(key=lambda r: r["started_seconds"])
        first = next((r["finished_seconds"] for r in values if r["ok"]), None)
        failures = [r for r in values if not r["ok"]]
        last_failed = max((r["started_seconds"] for r in failures), default=None)
        tail = next((r["finished_seconds"] for r in values if r["ok"] and (last_failed is None or r["started_seconds"] > last_failed)), None)
        series.append({"scope": key[0], "ip": key[1], "transport": key[2], "kind": key[3], "first_success_seconds": first, "successful_tail_seconds": tail, "failures": len(failures), "total": len(values), "last_ok": values[-1]["ok"]})
    save("summary.json", {"query_count": len(rows), "counts": [{"transport": k[0], "result": k[1], "ok": k[2], "count": v} for k, v in sorted(counts.items())], "series": series})


async def run():
    mapping, ips, current = await discover()
    metadata = {"utc": utc(), "zone": ALLOWED_ZONE, "nameservers": mapping, "ips": ips, "currently_advertised_ips": current, "revision": os.environ.get("GITHUB_SHA"), "replica": os.environ.get("PROBE_REPLICA"), "query_timeout_seconds": 3, "ttl": 600, "offsets": OFFSETS, "initial_delays": DELAYS}
    try:
        request = urllib.request.Request("http://169.254.169.254/metadata/instance/compute?api-version=2021-02-01", headers={"Metadata": "true"})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=3) as response:
            metadata["azure_location"] = json.load(response).get("location")
    except Exception as exc:
        metadata["metadata_error"] = type(exc).__name__
    save("metadata.json", metadata)
    print(json.dumps(metadata), flush=True)
    cloud = await asyncio.to_thread(Cloud)
    global_limit = asyncio.Semaphore(64)
    limits = {ip: asyncio.Semaphore(4) for ip in ips}
    try:
        for round_no in range(1, 4):
            async with asyncio.TaskGroup() as group:
                for delay in DELAYS:
                    entry = cloud.reserve(round_no, delay)
                    epoch = await asyncio.to_thread(cloud.create, entry)
                    group.create_task(measure(entry, epoch, ips, global_limit, limits))
                    await asyncio.to_thread(cloud.verify, entry)
                print(json.dumps({"round": round_no, "state": "sampling", "utc": utc()}), flush=True)
            print(json.dumps({"round": round_no, "state": "complete", "utc": utc()}), flush=True)
        summarize()
    finally:
        await asyncio.to_thread(cloud.cleanup)


def validate():
    assert list(OFFSETS) == sorted(set(OFFSETS))
    for delay in DELAYS:
        assert delay in (0, 5, 10, 30)
        assert delay in OFFSETS
    message = dns.message.make_query("vanilla.primary.example.test.", "A", flags=0, use_edns=False)
    assert message.flags == 0 and message.edns == -1
    print("diagnostic syntax, schedule and DNS query flags validated; no cloud access")


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
