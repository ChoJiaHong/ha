import json
from pathlib import Path

from syncer.main import md5_bytes, hash_dict, FileCRSyncer


class FakeAPI:
    def __init__(self):
        self.store = {}

    def get_namespaced_custom_object(self, group, version, namespace, plural, name):
        return self.store.get((plural, name), {})

    def patch_namespaced_custom_object(self, group, version, namespace, plural, name, body):
        self.store[(plural, name)] = body


def test_hash():
    h1 = hash_dict({"a": 1})
    h2 = hash_dict({"a": 1})
    h3 = hash_dict({"a": 2})
    assert h1 == h2
    assert h1 != h3
    assert md5_bytes(b"abc") == "900150983cd24fb0d6963f7d28e17f72"


def test_file_io(tmp_path):
    path = tmp_path / "state.json"
    data = {"foo": "bar"}
    syncer = FileCRSyncer({}, FakeAPI(), "g", "v", "n")
    syncer.write_file(str(path), data)
    assert path.exists()
    loaded = syncer.load_file(str(path))
    assert loaded == data


def test_sync_file_to_cr(tmp_path):
    path = tmp_path / "state.json"
    data = {"foo": "bar"}
    path.write_text(json.dumps(data))
    api = FakeAPI()
    file_map = {str(path): ("states", "example")}
    syncer = FileCRSyncer(file_map, api, "g", "v", "n")
    syncer.sync_once()
    assert api.store[("states", "example")] == {"spec": data}
