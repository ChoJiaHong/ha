# Syncer 开发规范

## 项目目标

构建一个 Sidecar 组件，使本地 JSON 文件（被现有 Controller 使用）与 Kubernetes 自定义资源（CR）保持同步，无需修改 Controller 逻辑。

## Controller 操作的文件

```
Controller/information/
├── nodestatus.json
├── service.json
├── serviceSpec.json
└── subscription.json
```

## 同步目标

| 文件                  | CRD                                         | CR 名称               | Plural          |
| ------------------- | ------------------------------------------- | ------------------- | --------------- |
| `service.json`      | `Data` in `services.ha.example.com/v1`      | `service-info`      | `services`      |
| `serviceSpec.json`  | `Data` in `servicespecs.ha.example.com/v1`  | `servicespec-info`  | `servicespecs`  |
| `subscription.json` | `Data` in `subscriptions.ha.example.com/v1` | `subscription-info` | `subscriptions` |
| `nodestatus.json`   | `Data` in `nodestatuses.ha.example.com/v1`  | `nodestatus-info`   | `nodestatuses`  |

## 同步行为

* 本地文件变更会更新对应的 CR。
* CR 的外部变更会同步写回本地文件。
* 使用 MD5 哈希检测差异，防止同步回环。
* 启动时，若 CR 不存在，则自动创建空 CR。

## 部署方式

将 syncer 作为 sidecar 部署，与 controller 共享一个 `emptyDir` 卷。示例：

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
