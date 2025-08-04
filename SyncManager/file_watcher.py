"""Watch local files and push changes to Kubernetes custom resources."""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .k8s_client import get_custom_object, patch_custom_object
from .utils import canonical_json, compute_checksum


class SyncPair:
    """Mapping between a file and a Kubernetes custom resource."""

    def __init__(
        self,
        group: str,
        version: str,
        plural: str,
        name: str,
        namespace: str,
        file: str,
    ):
        self.group = group
        self.version = version
        self.plural = plural
        self.name = name
        self.namespace = namespace
        self.file = file
        self.checksum: Optional[str] = None
        self.resource_version: Optional[str] = None


class FileChangeHandler(FileSystemEventHandler):
    def __init__(self, pair: SyncPair, api):
        super().__init__()
        self.pair = pair
        self.api = api

    def on_modified(self, event):
        if event.src_path != os.path.abspath(self.pair.file):
            return
        try:
            with open(self.pair.file, "r") as f:
                data = json.load(f)
        except Exception as exc:  # pragma: no cover - best effort
            logging.warning("Failed to read %s: %s", self.pair.file, exc)
            return

        serialized = canonical_json(data)
        checksum = compute_checksum(serialized)
        if checksum == self.pair.checksum:
            return

        # Detect conflicts using resourceVersion
        obj = get_custom_object(
            self.api,
            self.pair.group,
            self.pair.version,
            self.pair.namespace,
            self.pair.plural,
            self.pair.name,
        )
        rv = obj["metadata"].get("resourceVersion")
        if self.pair.resource_version and rv != self.pair.resource_version:
            logging.warning(
                "Conflict detected for %s: remote resourceVersion %s != %s",
                self.pair.name,
                rv,
                self.pair.resource_version,
            )
            remote_serialized = canonical_json(obj.get("spec", {}))
            with open(self.pair.file, "w") as f:
                f.write(remote_serialized)
            self.pair.checksum = compute_checksum(remote_serialized)
            self.pair.resource_version = rv
            return

        body = {"spec": data}
        updated = patch_custom_object(
            self.api,
            self.pair.group,
            self.pair.version,
            self.pair.namespace,
            self.pair.plural,
            self.pair.name,
            body,
        )
        self.pair.resource_version = updated["metadata"].get("resourceVersion")
        self.pair.checksum = checksum


def start_file_watch(pair: SyncPair, api) -> Observer:
    """Start watching the file of the sync pair."""
    handler = FileChangeHandler(pair, api)
    observer = Observer()
    directory = os.path.dirname(os.path.abspath(pair.file)) or "."
    observer.schedule(handler, directory, recursive=False)
    observer.start()
    return observer
