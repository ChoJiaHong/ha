import os
import json
import time
import hashlib
import logging
from pathlib import Path
from typing import Dict, Tuple

from kubernetes import client, config

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')


def load_kube_config(in_cluster: bool) -> None:
    if in_cluster:
        config.load_incluster_config()
    else:
        config.load_kube_config()


def parse_file_map(env: str) -> Dict[str, Tuple[str, str]]:
    mapping: Dict[str, Tuple[str, str]] = {}
    for line in env.strip().splitlines():
        if not line:
            continue
        path, target = line.split('=')
        plural, name = target.split(':')
        mapping[path] = (plural, name)
    return mapping


def md5_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


def hash_dict(d: Dict) -> str:
    return md5_bytes(json.dumps(d, sort_keys=True).encode())


class FileCRSyncer:
    def __init__(self, file_map: Dict[str, Tuple[str, str]], api: client.CustomObjectsApi,
                 group: str, version: str, namespace: str, interval: int = 5) -> None:
        self.file_map = file_map
        self.api = api
        self.group = group
        self.version = version
        self.namespace = namespace
        self.interval = interval
        self.state = {path: {'file': None, 'cr': None} for path in file_map}

    def load_file(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def write_file(self, path: str, data: Dict) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w') as f:
            json.dump(data, f, indent=2, sort_keys=True)

    def read_cr(self, plural: str, name: str) -> Dict:
        try:
            return self.api.get_namespaced_custom_object(
                self.group, self.version, self.namespace, plural, name)
        except Exception as exc:  # pragma: no cover - log only
            logging.error("read CR failed: %s", exc)
            return {}

    def patch_cr(self, plural: str, name: str, spec: Dict) -> None:
        body = {"spec": spec}
        try:
            self.api.patch_namespaced_custom_object(
                self.group, self.version, self.namespace, plural, name, body)
        except Exception as exc:  # pragma: no cover - log only
            logging.error("patch CR failed: %s", exc)

    def sync_once(self) -> None:
        for path, (plural, name) in self.file_map.items():
            file_data = self.load_file(path)
            cr_obj = self.read_cr(plural, name)
            cr_spec = cr_obj.get('spec', {})

            file_hash = hash_dict(file_data) if file_data else None
            cr_hash = hash_dict(cr_spec) if cr_spec else None
            last = self.state[path]

            if last['file'] is None and last['cr'] is None:
                if file_hash:
                    logging.info('initial sync: file -> CR for %s', path)
                    self.patch_cr(plural, name, file_data)
                    self.state[path] = {'file': file_hash, 'cr': file_hash}
                elif cr_hash:
                    logging.info('initial sync: CR -> file for %s', path)
                    self.write_file(path, cr_spec)
                    self.state[path] = {'file': cr_hash, 'cr': cr_hash}
                continue

            if file_hash != last['file']:
                logging.info('file changed: updating CR %s/%s', plural, name)
                self.patch_cr(plural, name, file_data)
                self.state[path] = {'file': file_hash, 'cr': file_hash}
            elif cr_hash != last['cr']:
                logging.info('CR changed: updating file %s', path)
                self.write_file(path, cr_spec)
                self.state[path] = {'file': cr_hash, 'cr': cr_hash}

    def run(self) -> None:
        while True:
            self.sync_once()
            time.sleep(self.interval)


def main() -> None:
    file_map_env = os.environ.get('FILE_MAP')
    if not file_map_env:
        raise SystemExit('FILE_MAP is required')

    file_map = parse_file_map(file_map_env)
    group = os.environ.get('CRD_GROUP', 'ha.example.com')
    version = os.environ.get('CRD_VERSION', 'v1')
    namespace = os.environ.get('CRD_NAMESPACE', 'default')
    in_cluster = os.environ.get('IN_CLUSTER', 'true').lower() == 'true'
    interval = int(os.environ.get('SYNC_INTERVAL', '5'))

    load_kube_config(in_cluster)
    api = client.CustomObjectsApi()

    syncer = FileCRSyncer(file_map, api, group, version, namespace, interval)
    syncer.run()


if __name__ == '__main__':
    main()
