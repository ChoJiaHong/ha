"""Watch Kubernetes custom resources and write changes to local files."""

import logging
from kubernetes.watch import Watch

from .k8s_client import get_custom_object
from .utils import canonical_json, compute_checksum


def start_cr_watch(pair, api):
    """Stream MODIFIED events of the custom resource and update the file."""
    watcher = Watch()
    stream = watcher.stream(
        api.get_namespaced_custom_object,
        pair.group,
        pair.version,
        pair.namespace,
        pair.plural,
        pair.name,
        timeout_seconds=0,
    )
    for event in stream:
        if event.get("type") != "MODIFIED":
            continue
        obj = event["object"]
        rv = obj["metadata"].get("resourceVersion")
        serialized = canonical_json(obj.get("spec", {}))
        checksum = compute_checksum(serialized)
        if checksum == pair.checksum:
            pair.resource_version = rv
            continue
        try:
            with open(pair.file, "w") as f:
                f.write(serialized)
        except Exception as exc:  # pragma: no cover
            logging.warning("Failed to write %s: %s", pair.file, exc)
            continue
        pair.checksum = checksum
        pair.resource_version = rv
