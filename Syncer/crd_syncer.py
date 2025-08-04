import os
import time
import json
import hashlib
import logging
from typing import Dict, Tuple

from kubernetes import client, config
from kubernetes.client import ApiException

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def load_kube_config() -> None:
    """Load Kubernetes configuration based on IN_CLUSTER flag."""
    in_cluster = os.environ.get("IN_CLUSTER", "false").lower() == "true"
    if in_cluster:
        config.load_incluster_config()
    else:
        config.load_kube_config()


def parse_file_map(raw: str) -> Dict[str, Tuple[str, str]]:
    """Parse FILE_MAP env into mapping {filepath: (plural, name)}."""
    mapping: Dict[str, Tuple[str, str]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            path, target = line.split("=")
            plural, name = target.split(":")
            mapping[path] = (plural, name)
        except ValueError:
            logging.warning("Invalid FILE_MAP entry: %s", line)
    return mapping


def md5sum(data: str) -> str:
    return hashlib.md5(data.encode("utf-8")).hexdigest()


def ensure_cr(api: client.CustomObjectsApi, group: str, version: str,
              namespace: str, plural: str, name: str) -> Dict:
    """Ensure the custom resource exists, return its body."""
    try:
        return api.get_namespaced_custom_object(group, version, namespace, plural, name)
    except ApiException as e:
        if e.status == 404:
            body = {
                "apiVersion": f"{group}/{version}",
                "kind": "Data",
                "metadata": {"name": name},
                "spec": {"data": {}}
            }
            api.create_namespaced_custom_object(group, version, namespace, plural, body)
            logging.info("Created %s/%s", plural, name)
            return body
        raise


def get_cr_data(body: Dict) -> Dict:
    return body.get("spec", {}).get("data", {})


def sync_loop():
    file_map_raw = os.environ.get("FILE_MAP", "")
    if not file_map_raw:
        raise RuntimeError("FILE_MAP env is required")
    mappings = parse_file_map(file_map_raw)

    group = os.environ.get("CRD_GROUP", "ha.example.com")
    version = os.environ.get("CRD_VERSION", "v1")
    namespace = os.environ.get("NAMESPACE", "default")
    interval = float(os.environ.get("SYNC_INTERVAL", "5"))

    api = client.CustomObjectsApi()

    state: Dict[str, Dict[str, str]] = {}
    for path, (plural, name) in mappings.items():
        body = ensure_cr(api, group, version, namespace, plural, name)
        cr_md5 = md5sum(json.dumps(get_cr_data(body), sort_keys=True))
        if os.path.exists(path):
            with open(path) as f:
                content = f.read()
        else:
            content = json.dumps({}, indent=2, sort_keys=True)
            with open(path, "w") as f:
                f.write(content)
        file_md5 = md5sum(content)
        state[path] = {"file_md5": file_md5, "cr_md5": cr_md5}

    while True:
        for path, (plural, name) in mappings.items():
            st = state[path]

            # read file
            try:
                with open(path) as f:
                    file_content = f.read()
            except FileNotFoundError:
                file_content = json.dumps({}, indent=2, sort_keys=True)
                with open(path, "w") as f:
                    f.write(file_content)
            file_md5 = md5sum(file_content)

            # read CR
            body = api.get_namespaced_custom_object(group, version, namespace, plural, name)
            cr_content = json.dumps(get_cr_data(body), indent=2, sort_keys=True)
            cr_md5 = md5sum(cr_content)

            if file_md5 != st["file_md5"] and file_md5 != st["cr_md5"]:
                # file changed -> update CR
                logging.info("%s changed, updating CR %s/%s", path, plural, name)
                patch_body = {"spec": {"data": json.loads(file_content)}}
                api.patch_namespaced_custom_object(group, version, namespace, plural, name, patch_body)
                st["file_md5"] = file_md5
                st["cr_md5"] = file_md5
            elif cr_md5 != st["cr_md5"] and cr_md5 != st["file_md5"]:
                # CR changed -> update file
                logging.info("CR %s/%s changed, writing to %s", plural, name, path)
                with open(path, "w") as f:
                    f.write(cr_content)
                st["file_md5"] = cr_md5
                st["cr_md5"] = cr_md5
        time.sleep(interval)


if __name__ == "__main__":
    load_kube_config()
    sync_loop()
