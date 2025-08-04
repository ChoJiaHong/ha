# 假設Docker、NVIDIA Driver、NVIDIA Container Runtime都已安裝且可用

# 關閉swap（只需第一次安裝時做，若沒動過可略過）
# sudo vim /etc/fstab

# 進入ARHA_Project專案目錄
cd /你的/ARHA_Project/路徑

# 給computing node腳本執行權限（如果沒改過可略過）
chmod +x ./k8s_computing_install.sh

# 編輯k8s_computing_install.sh（38,39行貼PC1新紅框內容，43行換PC1帳號/IP）

# 執行腳本（不可用sudo）
. /k8s_computing_install.sh
# <--- 執行過程會需要輸入PC1密碼

# 加入集群後，等PC1確認你已Ready即可
