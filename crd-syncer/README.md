# CRD Syncer

A lightweight synchronizer that keeps JSON state files and Kubernetes custom resources (CRs) in sync. Existing applications can continue using local JSON files while the syncer mirrors changes to Kubernetes.

## Installation

### Helm (optional)
```bash
helm install crd-syncer ./charts
```

### kubectl
```bash
kubectl apply -f deployment.yaml
```

### Docker
```bash
docker build -t crd-syncer .
docker run --rm -e FILE_MAP="/data/state.json=states:example" \
  -v $(pwd)/data:/data crd-syncer
```

## Quick Start
1. Deploy the [CRD](examples/crd.yaml).
2. Deploy the syncer using the [example deployment](examples/deployment.yaml) or the provided `deployment.yaml`.
3. Write to your JSON file and watch the corresponding Custom Resource update automatically.

## Customizing Sync Rules
`FILE_MAP` defines mappings between files and Custom Resources. Each line follows:
```
/path/file.json=plural:name
```
Multiple mappings are supported using newlines.

## Examples
See the [examples](examples) directory for a sample CRD and deployment manifest.

## Troubleshooting
* Ensure the CRD exists and the syncer has RBAC permissions to read/write it.
* Verify the `FILE_MAP` paths are mounted inside the container.

## License
[MIT](LICENSE)
