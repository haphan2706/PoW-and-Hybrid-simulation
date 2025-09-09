import hashlib

def sha256(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()

def H_hex(*parts: bytes) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.hexdigest()

def H_int(*parts: bytes) -> int:
    return int.from_bytes(sha256(b"".join(parts)), "big")
