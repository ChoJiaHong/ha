# Syncer 開發規範

## 專案目標

建置一個 Sidecar 元件，將現有控制器所使用的本地 JSON 檔案，與 Kubernetes Custom Resource (CR) 同步，而不需修改控制器邏輯。

## 控制器操作的檔案

```
Controller/information/
├── nodestatus.json
├── service.json
├── serviceSpec.json
└── subscription.json
```

## 同步對象

| 檔案                  | CRD                                         | CR 名稱               | 複數名稱            |
| ------------------- | ------------------------------------------- | ------------------- | --------------- |
| `service.json`      | `Data` in `services.ha.example.com/v1`      | `service-info`      | `services`      |
| `serviceSpec.json`  | `Data` in `servicespecs.ha.example.com/v1`  | `servicespec-info`  | `servicespecs`  |
| `subscription.json` | `Data` in `subscriptions.ha.example.com/v1` | `subscription-info` | `subscriptions` |
| `nodestatus.json`   | `Data` in `nodestatuses.ha.example.com/v1`  | `nodestatus-info`   | `nodestatuses`  |

## 同步行為

* 本地檔案變更會更新對應的 CR。
* 外部對 CR 的變更也會回寫到本地檔案。
* 透過 MD5 雜湊值偵測差異，避免同步回圈。
* 啟動時，若 CR 不存在則建立空的 CR。

## 部署方式

將 syncer 以 sidecar 形式部署，並與 controller 共用 `emptyDir` 卷。範例如下：

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
