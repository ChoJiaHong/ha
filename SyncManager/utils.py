import json
import hashlib

def canonical_json(data):
    """Return a canonical JSON string with sorted keys."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))

def compute_checksum(data):
    """Compute MD5 checksum of canonical JSON data."""
    if not isinstance(data, str):
        data = canonical_json(data)
    return hashlib.md5(data.encode("utf-8")).hexdigest()
