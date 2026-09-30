import zlib


def region_bytes(values):
    header = bytearray(8192)
    sectors = []
    for index, value in enumerate(values):
        header[index * 4 : index * 4 + 4] = ((index + 2) * 256 + 1).to_bytes(4, "big")
        payload = zlib.compress(value.encode())
        sectors.append(
            ((len(payload) + 1).to_bytes(4, "big") + b"\x02" + payload).ljust(
                4096, b"\0"
            )
        )
    return bytes(header) + b"".join(sectors)


def chunk_value(path, index):
    content = path.read_bytes()
    offset = int.from_bytes(content[index * 4 : index * 4 + 3], "big") * 4096
    if not offset:
        return None
    length = int.from_bytes(content[offset : offset + 4], "big")
    assert content[offset + 4] == 2
    return zlib.decompress(content[offset + 5 : offset + 4 + length]).decode()
