import json
import os
import sys
from pathlib import Path


def write_config(path: Path) -> None:
    required = ("HUAWEICLOUD_AK", "HUAWEICLOUD_SK", "HUAWEICLOUD_DNS_ZONE")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError("dns-e2e requires configuration: " + ", ".join(missing))
    config = {"dns": {"huawei": {
        "domain": os.environ["HUAWEICLOUD_DNS_ZONE"],
        "managed_sub_domain": os.environ.get("HUAWEICLOUD_DNS_PARENT", ""),
        "prefix": "run",
        "region": os.environ.get("HUAWEICLOUD_DNS_REGION") or "cn-north-4",
        "ttl": 600,
        "ak": os.environ["HUAWEICLOUD_AK"],
        "sk": os.environ["HUAWEICLOUD_SK"],
    }}}
    with open(path, "w", opener=lambda name, flags: os.open(name, flags, 0o600)) as stream:
        json.dump(config, stream)
    path.chmod(0o600)


if __name__ == "__main__":
    try:
        write_config(Path(sys.argv[1]))
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
