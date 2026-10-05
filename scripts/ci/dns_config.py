import json
import os
import sys
from pathlib import Path


def write_config(path: Path, providers: list[str]) -> None:
    if not isinstance(providers, list) or any(
        not isinstance(provider, str) or provider not in {"huawei", "dnspod"}
        for provider in providers
    ) or len(providers) != len(set(providers)):
        raise ValueError("API shard requires a list of distinct supported providers")
    dns = {}
    if "huawei" in providers:
        required = ("HUAWEICLOUD_AK", "HUAWEICLOUD_SK", "HUAWEICLOUD_DNS_ZONE")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise ValueError("Huawei DNS requires configuration: " + ", ".join(missing))
        dns["huawei"] = {
            "domain": os.environ["HUAWEICLOUD_DNS_ZONE"],
            "managed_sub_domain": os.environ.get("HUAWEICLOUD_DNS_PARENT", ""),
            "region": os.environ.get("HUAWEICLOUD_DNS_REGION") or "cn-north-4",
            "ttl": 600,
            "ak": os.environ["HUAWEICLOUD_AK"],
            "sk": os.environ["HUAWEICLOUD_SK"],
        }
    if "dnspod" in providers:
        try:
            config = json.loads(os.environ.get("E2E_EXTERNAL_CONFIG", ""))
            dnspod = config["dns"]["dnspod"]
        except (ValueError, KeyError, TypeError):
            raise ValueError("DNSPod requires E2E_EXTERNAL_CONFIG containing dns.dnspod") from None
        if not isinstance(dnspod, dict) or any(not dnspod.get(key) for key in ("domain", "id", "key")):
            raise ValueError("dns.dnspod requires domain, id and key")
        dns["dnspod"] = dnspod
    with open(path, "w", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        if dns:
            json.dump({"dns": dns}, stream)
    path.chmod(0o600)


if __name__ == "__main__":
    try:
        write_config(Path(sys.argv[1]), json.loads(os.environ["E2E_PROVIDERS"]))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
