CRD Syncer
此 sidecar 元件負責將本地 JSON 檔案與 Kubernetes 自訂資源進行同步。

環境變數

* **FILE\_MAP**：以換行分隔的對應關係，格式為 `file_path=plural:name`。
* **CRD\_GROUP**：CRD 的 API group（例如 ha.example.com）。
* **CRD\_VERSION**：CRD 的 API 版本（例如 v1）。
* **NAMESPACE**：自訂資源所屬的命名空間，預設為 default。
* **IN\_CLUSTER**：在叢集內執行時設為 true。
* **SYNC\_INTERVAL**：輪詢間隔秒數，預設為 5。

用法
Syncer 會使用 MD5 雜湊值，雙向同步檔案與 CR，避免同步時發生回饋迴圈。
範例部署方式（使用 emptyDir 卷）請參考專案文件。
