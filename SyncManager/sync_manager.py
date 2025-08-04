"""Entry point for synchronizing files and Kubernetes custom resources."""

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import List

import yaml

from .file_watcher import SyncPair, start_file_watch
from .cr_watcher import start_cr_watch
from .k8s_client import create_api_client, get_custom_object
from .utils import canonical_json, compute_checksum

CONFIG_ENV = "SYNC_CONFIG_PATH"


def load_sync_pairs(config_path: str) -> List[SyncPair]:
    with open(config_path, "r") as f:
        data = yaml.safe_load(f) or {}
    pairs = []
    for item in data.get("sync_pairs", []):
        pair = SyncPair(
            group=item["group"],
            version=item["version"],
            plural=item["plural"],
            name=item["name"],
            namespace=item["namespace"],
            file=item["file"],
        )
        pairs.append(pair)
    return pairs


def initialize_pairs(api, pairs: List[SyncPair]):
    for pair in pairs:
        obj = get_custom_object(
            api,
            pair.group,
            pair.version,
            pair.namespace,
            pair.plural,
            pair.name,
        )
        spec = obj.get("spec", {})
        serialized = canonical_json(spec)
        pair.checksum = compute_checksum(serialized)
        pair.resource_version = obj["metadata"].get("resourceVersion")
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(pair.file)), exist_ok=True)
        with open(pair.file, "w") as f:
            f.write(serialized)


def main():
    config_path = os.environ.get(CONFIG_ENV, "sync_config.yaml")
    api = create_api_client()
    pairs = load_sync_pairs(config_path)
    initialize_pairs(api, pairs)

    observers = []
    threads = []
    for pair in pairs:
        observers.append(start_file_watch(pair, api))
        t = threading.Thread(target=start_cr_watch, args=(pair, api), daemon=True)
        t.start()
        threads.append(t)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        for obs in observers:
            obs.stop()
        for obs in observers:
            obs.join()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
