package dns

const cleanupScript = `import json
import sys
import time
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text())
provider = data["provider"]
scope = data["scope"]
config = data["config"]
domain = config["domain"]
assert scope.startswith(config["prefix"] + "-")
assert len(scope.rsplit("-", 1)[1]) == 12

def owned(name, kind):
    return name.endswith("." + scope) and (
        (kind in ("A", "AAAA", "CNAME") and name.startswith("*."))
        or (kind == "SRV" and name.startswith("_minecraft._tcp."))
    )

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
            result.extend((r.Name, r.Type, r.RecordId) for r in page if owned(r.Name, r.Type))
            if len(page) < 100:
                return result
            offset += len(page)
    def delete(record):
        req = models.DeleteRecordRequest()
        req.from_json_string(json.dumps({"Domain": domain, "RecordId": record[2]}))
        client.DeleteRecord(req)
    return records, delete

def huawei():
    from huaweicloudsdkcore.auth.credentials import BasicCredentials
    from huaweicloudsdkcore.http.http_config import HttpConfig
    from huaweicloudsdkdns.v2 import DnsClient, ListPublicZonesRequest, ListRecordSetsByZoneRequest, DeleteRecordSetsRequest
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
                    if owned(name, record.type):
                        result.append((name, record.type, record.id))
            if len(page) < 500:
                return result
            offset += len(page)
    def delete(record):
        client.delete_record_sets(DeleteRecordSetsRequest(zone_id=zone_id, recordset_id=record[2]))
    return records, delete

try:
    records, delete = dnspod() if provider == "dnspod" else huawei()
    current = records()
    if sys.argv[2] == "check":
        if current:
            raise ValueError("generated test scope already contains records; refusing mutation")
    elif sys.argv[2] == "cleanup":
        for record in current:
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
    print(json.dumps({"error_type": type(exc).__name__, "domain": domain, "scope": scope}))
    sys.exit(1)
`
