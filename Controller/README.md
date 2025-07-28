controller.py:

    compute_frequnecy() -> 頻率調整模組，輸入是1.要計算頻率的服務類型 2.要計算的Agent數量

    deploy_service() -> AI推論服務部署模組，輸入是1.系統嘗試要部署的服務類型 

    adjust_frequency() -> 實際上調整Agent傳送頻率的函式 

    is_pod_terminating() -> 檢查Pod是否正在刪除中，ex. pose-workergpu-30501在刪除時，要部署新服務的話透過這個函式可以避免deploy_pod()使用到pose-workergpu-30501這個名字命名新的Pod，造成K8s API報錯

    subscribe API -> 訂閱模組，有Lock變數

    alert API -> 故障處理模組，有Lock變數，有新增錯誤類型為pod_failure的case


controller-deployment.yaml:

    spec.template.spec.containers.[0].env為讓俞諠實驗時方便更換演算法用的

optimizer.py:

    放置各種演算法，本論文使用的演算法為optimize()