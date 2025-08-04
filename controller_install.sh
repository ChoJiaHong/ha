kubectl create namespace arha-system
kubectl apply -f arha-logs-pv.yaml
kubectl apply -f arha-logs-pvc.yaml
kubectl apply -f arha-pv.yaml
kubectl apply -f arha-pvc.yaml
kubectl apply -f Controller/controller-rolebinding.yaml
kubectl apply -f Controller/controller-deployment.yaml
kubectl apply -f Controller/controller-service.yaml