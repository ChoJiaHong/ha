# （假設Docker、curl、openssh-server都已安裝且正常，若未安裝才需補裝）

# 關閉swap（只需第一次安裝時做，若沒動過可略過）
# sudo vim /etc/fstab

# 進入ARHA_Project專案目錄
cd ~/git_repo/ha

# 再次給master腳本執行權限（如果有還在則可略過）
chmod +x ./k8s_master_install.sh

# 執行master安裝腳本（不可用sudo）
./k8s_master_install.sh
# <--- 記下紅框內容（token/join指令，留給node用）

# 設定K8s
kubectl edit cm -n kube-system kubelet-config
# 將 data.kubelet.healthzBindAddress 改成 0.0.0.0

sudo kubeadm upgrade node phase kubelet-config

sudo vim /etc/kubernetes/manifests/kube-controller-manager.yaml
# spec.containers.command 加入
# - --node-monitor-grace-period=15s

kubectl edit cm -n kube-flannel kube-flannel-cfg
# 網路配置改host-gw

kubectl get pods -n kube-flannel -o name | xargs kubectl delete -n kube-flannel

# 檢查節點與Pods狀態
kubectl get nodes
kubectl get pods -A

# 標記節點（label）
kubectl label nodes {PC1主機名稱} arha-node-type=controller-node
kubectl label nodes {PC2主機名稱} arha-node-type=computing-node
kubectl label nodes {PC3主機名稱} arha-node-type=computing-node
