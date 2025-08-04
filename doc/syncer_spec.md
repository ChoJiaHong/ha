# Syncer Development Specification

## Project Goal

Build a sidecar component that keeps local JSON files used by the existing controller
in sync with Kubernetes custom resources (CRs) without modifying the controller logic.

## Files Operated by the Controller

```
Controller/information/
├── nodestatus.json
├── service.json
├── serviceSpec.json
└── subscription.json
```

## Synchronization Targets

| File | CRD | CR Name | Plural |
| ---- | --- | ------- | ------ |
| `service.json` | `Data` in `services.ha.example.com/v1` | `service-info` | `services` |
| `serviceSpec.json` | `Data` in `servicespecs.ha.example.com/v1` | `servicespec-info` | `servicespecs` |
| `subscription.json` | `Data` in `subscriptions.ha.example.com/v1` | `subscription-info` | `subscriptions` |
| `nodestatus.json` | `Data` in `nodestatuses.ha.example.com/v1` | `nodestatus-info` | `nodestatuses` |

## Synchronization Behavior

- Changes to local files update the corresponding CR.
- External changes to a CR are written back to the local file.
- MD5 hashes detect differences and prevent feedback loops.
- On startup, the syncer creates empty CRs when they do not exist.

## Deployment

Deploy the syncer as a sidecar sharing an `emptyDir` volume with the controller. Example:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: controller-with-syncer
  namespace: default
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ha-controller
  template:
    metadata:
      labels:
        app: ha-controller
    spec:
      volumes:
        - name: shared-data
          emptyDir: {}
      containers:
        - name: controller
          image: your-controller-image:latest
          volumeMounts:
            - mountPath: /data
              name: shared-data
        - name: crd-syncer
          image: your-crd-syncer-image:latest
          env:
            - name: FILE_MAP
              value: |
                /data/service.json=services:service-info
                /data/serviceSpec.json=servicespecs:servicespec-info
                /data/subscription.json=subscriptions:subscription-info
                /data/nodestatus.json=nodestatuses:nodestatus-info
            - name: CRD_GROUP
              value: ha.example.com
            - name: CRD_VERSION
              value: v1
            - name: IN_CLUSTER
              value: "true"
          volumeMounts:
            - mountPath: /data
              name: shared-data
```
