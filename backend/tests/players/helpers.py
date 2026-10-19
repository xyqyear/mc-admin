import hashlib


def make_online_uuid(seed: str) -> str:
    source = hashlib.md5(seed.encode()).hexdigest()
    return f"{source[:12]}4{source[13:16]}8{source[17:]}"


def make_offline_uuid(seed: str) -> str:
    source = hashlib.md5(seed.encode()).hexdigest()
    return f"{source[:12]}3{source[13:16]}8{source[17:]}"
