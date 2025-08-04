# CRD Syncer

This sidecar component synchronizes local JSON files with Kubernetes custom resources.

## Environment variables

- `FILE_MAP`: newline separated mappings in the form `file_path=plural:name`.
- `CRD_GROUP`: CRD API group (e.g. `ha.example.com`).
- `CRD_VERSION`: CRD API version (e.g. `v1`).
- `NAMESPACE`: namespace of the custom resources. Defaults to `default`.
- `IN_CLUSTER`: set to `true` when running inside a cluster.
- `SYNC_INTERVAL`: polling interval in seconds. Defaults to 5.

## Usage

The syncer keeps files and CRs in sync in both directions using MD5 hashes to
avoid feedback loops. An example deployment using an `emptyDir` volume is
available in the project documentation.
