import json
import re
import sys
import time
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
provider = data["provider"]
scope = data["scope"]
config = data["config"]
domain = config["domain"]
parent = config.get("managed_sub_domain", "")
pattern = re.escape(config["prefix"]) + r"-[0-9a-f]{12}" + (r"\." + re.escape(parent) if parent else "")
if not re.fullmatch(pattern, scope):
    raise ValueError("scope is outside the authorized namespace")

def owned(name, kind):
    return name.endswith("." + scope) and (
        (kind in ("A", "AAAA", "CNAME") and name.startswith("*."))
        or (kind == "SRV" and name.startswith("_minecraft._tcp."))
    )

guard_name = "_e2e-preserve." + scope
guard_value = '"mc-admin-e2e:' + scope + '"'

def scoped(name):
    return name == scope or name.endswith("." + scope)

def dnspod():
    from tencentcloud.common.credential import Credential
    from tencentcloud.common.profile.client_profile import ClientProfile
    from tencentcloud.common.profile.http_profile import HttpProfile
    from tencentcloud.dnspod.v20210323.dnspod_client import DnspodClient
    from tencentcloud.dnspod.v20210323 import models
    profile = ClientProfile(httpProfile=HttpProfile(reqTimeout=20))
    client = DnspodClient(Credential(config["id"], config["key"]), "", profile)
    def records():
        result, offset = [], 0
        while True:
            req = models.DescribeRecordListRequest()
            req.from_json_string(json.dumps({"Domain": domain, "Offset": offset, "Limit": 100}))
            response = client.DescribeRecordList(req)
            page = response.RecordList or []
            result.extend((r.Name, r.Type, r.RecordId, [r.Value], r.TTL) for r in page if scoped(r.Name))
            if len(page) < 100:
                return result
            offset += len(page)
    def delete(record):
        req = models.DeleteRecordRequest()
        req.from_json_string(json.dumps({"Domain": domain, "RecordId": record[2]}))
        client.DeleteRecord(req)
    def protect():
        req = models.CreateRecordRequest()
        req.from_json_string(json.dumps({"Domain": domain, "SubDomain": guard_name, "RecordType": "TXT", "RecordLine": "默认", "Value": guard_value, "TTL": config["ttl"]}))
        client.CreateRecord(req)
    return records, delete, protect

def huawei():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkcore.http.http_config import HttpConfig
    from huaweicloudsdkdns.v2 import DnsClient, ListPublicZonesRequest, ListRecordSetsByZoneRequest, DeleteRecordSetsRequest, CreateRecordSetRequest, CreateRecordSetRequestBody
    from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
    http = HttpConfig.get_default_config()
    http.timeout = 20
    client = DnsClient.new_builder().with_credentials(BasicCredentials(config["ak"], config["sk"])).with_region(DnsRegion.value_of(config["region"])).with_http_config(http).build()
    zones = client.list_public_zones(ListPublicZonesRequest(name=domain + ".", search_mode="equal", limit=500)).zones
    matching = [zone.id for zone in zones if zone.name == domain + "."]
    if len(matching) != 1:
        raise ValueError("test domain must identify exactly one public DNS zone")
    zone_id = matching[0]
    def records():
        result, offset = [], 0
        while True:
            page = client.list_record_sets_by_zone(ListRecordSetsByZoneRequest(zone_id=zone_id, limit=500, offset=offset)).recordsets or []
            for record in page:
                suffix = "." + domain + "."
                if record.name.endswith(suffix):
                    name = record.name[:-len(suffix)]
                    if scoped(name):
                        result.append((name, record.type, record.id, record.records, record.ttl))
            if len(page) < 500:
                return result
            offset += len(page)
    def delete(record):
        client.delete_record_sets(DeleteRecordSetsRequest(zone_id=zone_id, recordset_id=record[2]))
    def protect():
        client.create_record_set(CreateRecordSetRequest(zone_id=zone_id, body=CreateRecordSetRequestBody(name=guard_name + "." + domain + ".", type="TXT", ttl=config["ttl"], records=[guard_value])))
    return records, delete, protect

try:
    records, delete, protect = dnspod() if provider == "dnspod" else huawei()
    current = records()
    if sys.argv[2] == "inspect":
        guards = [r for r in current if r[0] == guard_name and r[1] == "TXT"]
        if len(guards) != 1 or [v.strip('"') for v in guards[0][3]] != [guard_value.strip('"')]:
            raise ValueError("unmanaged protection record changed or disappeared")
        print(json.dumps({"records": [{"name": r[0], "type": r[1], "id": r[2], "values": r[3], "ttl": r[4]} for r in current if owned(r[0], r[1])]}))
        sys.exit(0)
    elif sys.argv[2] == "protect":
        protect()
    elif sys.argv[2] == "check":
        if current:
            raise ValueError("generated test scope already contains records; refusing mutation")
    elif sys.argv[2] == "cleanup":
        for record in current:
            if owned(record[0], record[1]) or (record[0] == guard_name and record[1] == "TXT" and [v.strip('"') for v in record[3]] == [guard_value.strip('"')]):
                delete(record)
        for attempt in range(20):
            current = records()
            if not current:
                break
            time.sleep(1)
        if current:
            raise ValueError("test DNS records remain after scoped cleanup")
    else:
        raise ValueError("unknown external DNS helper operation")
    print(json.dumps({"remaining": len(current), "domain": domain, "scope": scope}))
except Exception as exc:
    print(json.dumps({"error_type": type(exc).__name__, "status": getattr(exc, "status_code", None), "error_code": getattr(exc, "error_code", None), "domain": domain, "scope": scope}))
    sys.exit(1)
