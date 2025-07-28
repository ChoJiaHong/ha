from fastapi import FastAPI, Request, HTTPException
from pydantic import BaseModel
import optimizer
from typing import List, Optional
import json
from kubernetes import client, config
from kubernetes.client.rest import ApiException
from Controller import crd_utils
from starlette.responses import JSONResponse
import copy
import yaml
import time
import requests
import concurrent.futures
import logging
import sys
import asyncio
import os

GPU_MEMORY_LABEL = "nvidia.com/gpu.memory"
IN_CLUSTER = True
crd_utils.IN_CLUSTER = IN_CLUSTER

LOG_FILE = './logdir/controller.log'

locked = False

# 讀取環境變數來決定使用哪個函式
function_name = os.getenv("OPTIMIZER_FUNCTION", "optimize")

# 動態獲取函式
optimize  = getattr(optimizer, function_name)

# 設定 logging，將所有日誌寫入到 LOG_FILE
logging.basicConfig(
    filename= LOG_FILE,
    format='%(asctime)s %(levelname)s: %(message)s',
    level=logging.INFO
)

# Helper functions for interacting with Kubernetes CRDs are provided in
# crd_utils. Import frequently used helpers for convenience.
from Controller.crd_utils import (
    load_service_data,
    save_service_data,
    load_servicespec_data,
    save_servicespec_data,
    load_subscription_data,
    save_subscription_data,
    load_nodestatus_data,
    save_nodestatus_data,
)

class SubscriptionRequest(BaseModel):
    ip: str
    port: int
    serviceType: str
    
def lifespan(app: FastAPI):
    # 初始化 NODE_STATUS_FILE
    config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    core_api = client.CoreV1Api()
    node_status_list = []

    # 獲取所有節點的標籤
    nodes = core_api.list_node().items
    for node in nodes:
        labels = node.metadata.labels
        if labels.get('arha-node-type') == 'computing-node':
            node_status_list.append(node.metadata.name)

    node_health_status = {}
    for node in node_status_list:
        ip = get_node_ip(node)
        if ip != "Error":
            try:
                if curl_health_check(ip).strip().lower() == 'ok':
                    node_health_status[node] = "healthy"
                else:
                    node_health_status[node] = "unhealthy"
            except Exception as e:
                node_health_status[node] = "unhealthy"
        else:
            node_health_status[node] = "unhealthy"

    save_nodestatus_data(node_health_status)
    yield

app = FastAPI(lifespan=lifespan)

# 中間件，用來紀錄每個 API 呼叫的詳情
@app.middleware("http")
async def log_requests(request: Request, call_next):
    # 取得 API 名稱 (路徑)、請求內容、來源 IP
    api_name = request.url.path
    request_body = await request.body()
    client_ip = request.client.host  # 取得來源 IP
    request_log = request_body.decode("utf-8") if request_body else None
    logging.info(f"{api_name} receive request {request_log} from IP: {client_ip}")

    # 呼叫 API 並取得回應
    try:
        response = await call_next(request)
        response_body = b"".join([chunk async for chunk in response.body_iterator])
        status_code = response.status_code  # 取得狀態碼
        response = JSONResponse(content=json.loads(response_body), status_code=status_code)
    except Exception as e:
        status_code = 500
        response = JSONResponse(content={"error": str(e)}, status_code=status_code)
    
    # 組合 log 訊息
    log_message = {
        "api_name": api_name,
        "client_ip": client_ip,  # 新增來源 IP 記錄
        "request": request_body.decode("utf-8") if request_body else None,
        "response": response.body.decode("utf-8"),
        "status_code": status_code  # 新增狀態碼記錄
    }
    response_log = response.body.decode("utf-8")
    # 將 log 訊息寫入到日誌檔
    # logging.info(json.dumps(log_message))
    logging.info(f"{api_name} response {response_log} and status code: {status_code}")
    
    return response

@app.post('/subscribe') # 接收訂閱請求
async def subscribe(request: Request, subscription: SubscriptionRequest):
    data = subscription
    agent_ip = data.ip
    agent_port = data.port
    serviceType = data.serviceType
    serviceNotFound = True

    if not agent_ip or not serviceType:
        raise HTTPException(status_code=400, detail="Invalid input")

    # 檢查請求中的serviceType是否存在
    try:
        serviceSpec_data = load_servicespec_data()
        for serviceSpec in serviceSpec_data:
            if serviceSpec['serviceType'] == serviceType:
                serviceNotFound = False
                break
        if serviceNotFound:
            raise HTTPException(status_code=500, detail="Service not in serviceSpec file")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ServiceSpec file not found")
    except json.decoder.JSONDecodeError:
        raise HTTPException(status_code=500, detail="ServiceSpec file is empty")

    global locked
    while locked:
        await asyncio.sleep(1)

    locked = True
    agentCounter = 1
    subscription_list = load_subscription_data()
    
    agentCounter += sum(1 for subscription in subscription_list if subscription['serviceType'] == serviceType)
    relation_list = compute_frequnecy(serviceType, agentCounter)

    newAgentCounter = 0
    for relation in relation_list:
        if relation['serviceType'] == serviceType:
            newAgentCounter += int(relation['currentConnection'])
    
    if newAgentCounter == (agentCounter-1):
        locked = False
        return 'reject the subscription' 
    elif newAgentCounter == agentCounter:
        save_service_data(relation_list)

        # 這邊adjust_frequency只會調整new agent以外的配對關係
        serviceIndex = adjust_frequency(serviceType)

        subscription_list = load_subscription_data()

        if serviceIndex is None:
            locked = False
            logging.info(f"Function adjust_frequency() return None")
            return 'controller program bug'
        else:
            subscription_list.append({
                "agentIP": agent_ip,
                "agentPort": agent_port,
                "podIP": relation_list[serviceIndex]['podIP'],
                "serviceType": serviceType,
                "nodeName": relation_list[serviceIndex]['nodeName']            
            })
        save_subscription_data(subscription_list)
        locked = False
        return {
            "IP": relation_list[serviceIndex]['hostIP'],
            "Port": relation_list[serviceIndex]['hostPort'],
            "Frequency": relation_list[serviceIndex]['currentFrequency']
        }
    else:
        locked = False
        return f"newAgentCounter={newAgentCounter} and agentCounter={agentCounter}" 

@app.post('/alert')
async def alert(request: Request):

    global locked
    while locked:
        await asyncio.sleep(1)
    locked = True    
    data = await request.json()
    alertType = data['alertType']
    alertContent = data['alertContent']

    # 處理Computing Node 故障的Case
    if alertType == 'workernode_failure':
        
        failnodeName = alertContent['nodeName']

        # 將故障的Computing Node上的所有服務從資料中清除
        try:
            service_list = load_service_data()
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail="Service file not found")
        
        failed_service_list = [item for item in service_list if item.get('nodeName') == failnodeName]
        service_list = [item for item in service_list if item.get('nodeName') != failnodeName]

        try:
            save_service_data(service_list)
        except Exception:
            raise HTTPException(status_code=500, detail="Failed to write to service file")

        # 處理故障節點上的所有service
        for failed_service in failed_service_list:
            
            # 從k8s中刪除service
            delete_pod(str(failed_service['serviceType'])+'-'+str(failed_service['nodeName'])+'-'+str(failed_service['hostPort']),'default')
            
            # 打開訂閱資料
            try:
                subscription_list = load_subscription_data()
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="Subscription file not found")
            
            # 若沒有任何終端訂閱故障service
            if failed_service['currentConnection'] == 0:
                continue

            # 若有終端訂閱故障之service
            agentCounter = 0
            agentCounter += sum(1 for subscription in subscription_list if subscription['serviceType'] == failed_service['serviceType'])
            relation_list = compute_frequnecy(str(failed_service['serviceType']), agentCounter)

            # 計算最後有多少Agent能使用服務 
            newAgentCounter = 0
            for relation in relation_list:
                if relation['serviceType'] == str(failed_service['serviceType']):
                    newAgentCounter += int(relation['currentConnection'])

            # 若非所有Agent都能使用服務
            if newAgentCounter < agentCounter:
                count = 0
                unsunscribedAgentCounter = agentCounter - newAgentCounter
                for i in reversed(range(len(subscription_list))):
                    if subscription_list[i]['podIP'] == str(failed_service['podIP']):
                        del subscription_list[i]
                        count += 1
                        if count >= unsunscribedAgentCounter:
                            break
                save_subscription_data(subscription_list)

            # 將新的配對方式存入service資料中
            save_service_data(relation_list)
            adjust_frequency(str(failed_service['serviceType']))        
    elif alertType == 'pod_failure':

        failPodName = str(alertContent['podName'])
        serviceType, nodeName, hostPort = failPodName.split('-')
        hostPort = int(hostPort)
        delete_pod(failPodName)

        service_list = load_service_data()

        # 找到符合條件的元素
        failed_service = next(
            (service for service in service_list if 
                service['serviceType'] == serviceType and 
                service['nodeName'] == nodeName and 
                service['hostPort'] == hostPort), 
            None  # 若找不到，返回 None
        )

        # 如果找到，則從 service_list 刪除
        if failed_service:
            service_list.remove(failed_service)

        save_service_data(service_list)

        if failed_service['currentConnection'] != 0:

            # 打開訂閱資料
            try:
                subscription_list = load_subscription_data()
            except FileNotFoundError:
                raise HTTPException(status_code=500, detail="Subscription file not found")
            
            agentCounter = 0
            agentCounter += sum(1 for subscription in subscription_list if subscription['serviceType'] == failed_service['serviceType'])
            relation_list = compute_frequnecy(str(failed_service['serviceType']), agentCounter)

            # 計算最後有多少Agent能使用服務 
            newAgentCounter = 0
            for relation in relation_list:
                if relation['serviceType'] == str(failed_service['serviceType']):
                    newAgentCounter += int(relation['currentConnection'])

            # 若非所有Agent都能使用服務
            if newAgentCounter < agentCounter:
                count = 0
                unsunscribedAgentCounter = agentCounter - newAgentCounter
                for i in reversed(range(len(subscription_list))):
                    if subscription_list[i]['podIP'] == str(failed_service['podIP']):
                        del subscription_list[i]
                        count += 1
                        if count >= unsunscribedAgentCounter:
                            break
                save_subscription_data(subscription_list)

            save_service_data(relation_list)

        adjust_frequency(str(failed_service['serviceType']))  
    locked = False
    return (f"message: Alert {alertType} handled successfully")

@app.post('/deploypod')
async def deploypod(request: Request):
    data = await request.json()
    node_name = str(data['nodeName'])
    hostPort = int(data['hostPort'])
    service_type = str(data['service_type'])
    serviceamountonnode = int(data['amount'])
    resp = deploy_pod(service_type,hostPort, node_name)

    try:
        service_data = load_service_data()
    except FileNotFoundError:
        return "Service file not found"

    serviceSpec_list = load_servicespec_data()
    
    for serviceSpec in serviceSpec_list:
        if serviceSpec['serviceType'] == service_type:
            workloadLimit = serviceSpec['workAbility'][node_name]
            frequencyLimit = serviceSpec['frequencyLimit']
    """        
    if  service_type == 'pose':
        if node_name == 'workergpu':
            workloadLimit = 70
        else:
            workloadLimit = 85
        frequencyLimit = [20,10]
    else:
        frequencyLimit = [30,15]
        if node_name == 'workergpu':
            workloadLimit = 170
        else:
            workloadLimit = 255
    """
    service_data.append({
        "podIP" : str(resp.status.pod_ip),
        "hostPort" : int(hostPort),
        "serviceType" : service_type,
        "currentConnection" : 0,
        "nodeName" : str(node_name),
        "hostIP" : str(resp.status.host_ip),
        "frequencyLimit" : frequencyLimit,
        "currentFrequency" : frequencyLimit[0],
        "workloadLimit" : workloadLimit/serviceamountonnode        
    })

    save_service_data(service_data)

    return 'deploy finish'

@app.post('/unsubscribe')
async def unsubscribe(request: Request):
    data = await request.json()
    agent_ip = request.client.host
    agent_port = data['port']

    try:
        subscription_data = load_subscription_data()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail= "Subscription file not found")
    
    new_subscription_data = []
    podip_set = set()

    for subscription in subscription_data:
        if str(subscription['agentIP']) == str(agent_ip) and int(subscription['agentPort']) == int(agent_port):
            podip_set.add(subscription['podIP'])
            message = "unsubscribe successfully"
        else:
            new_subscription_data.append(subscription)

    try:
        save_subscription_data(new_subscription_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to write to subscription file")
    
    try:
        service_data = load_service_data()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail= "Service file not found")
    if not service_data:
        raise HTTPException(status_code=404, detail= "Service file is empty")
    
    for service in service_data:
        # 更新服務當前的連線數
        if service['podIP'] in podip_set:
            service['currentConnection'] -=1 

    save_service_data(service_data)

    return {'message' : 'unsubscribe finish'}

def compute_frequnecy(serviceType: str, agentCounter: int):

    mustAutoScaling = True

    service_list = load_service_data()

    for service in service_list:
        if service['serviceType'] == serviceType:
            mustAutoScaling = False

    if not mustAutoScaling:
        status, relation_list = optimize(serviceType, agentCounter, service_list)
        for relation in relation_list:
            if relation['currentFrequency'] < relation['frequencyLimit'][0]:
                mustAutoScaling = True
                break
    if mustAutoScaling:
        deploy_service(serviceType)
        service_list = load_service_data()
        status, relation_list = optimize(serviceType, agentCounter, service_list)   
        while status=='fail':
            agentCounter -=1
            status, relation_list = optimize(serviceType, agentCounter, service_list)

    return relation_list

def deploy_service(serviceType: str):

    nodeDeployed_list = []
    workloadLimitAfterDeployed_dict = {}
    serviceSpec_dict = {}
    usedPort = set()

    serviceSpec_list = load_servicespec_data()

    for serviceSpec in serviceSpec_list:
        nodeDeployed_list.extend(serviceSpec["workAbility"].keys())
        serviceSpec_dict[serviceSpec['serviceType']] = {k: v for k, v in serviceSpec.items() if k != "serviceType"}
    nodeDeployed_list = list(set(nodeDeployed_list))

    config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    core_api = client.CoreV1Api()

    service_list = load_service_data()

    node_status_sync(nodeDeployed_list)

    # 更新節點當前狀態
    node_status_data = load_nodestatus_data()

    """
    檢查各節點是否同時滿足以下條件
    1. 有充足VRAM
    2. 尚未部署該類型之服務
    3. 部署後其他服務仍能獲得大於等於標準FPS之工作量上限
    """
    for nodeDeployed in nodeDeployed_list:

        if node_status_data[nodeDeployed] == 'unhealthy':
            continue
        canDeployOnThisNode = True
        gpuMemoryRequest = 0
        serviceTypeOnThisNode_list = []

        for service in service_list:
            if service['nodeName'] == nodeDeployed:
                if service['serviceType'] == serviceType:
                    canDeployOnThisNode = False
                    break 
                else:
                    serviceTypeOnThisNode_list.append(service['serviceType']) 
                    gpuMemoryRequest += serviceSpec_dict[service['serviceType']]['gpuMemoryRequest']

        nodeInformation = core_api.read_node(name=nodeDeployed)
        gpuMemory = int(nodeInformation.metadata.labels.get(GPU_MEMORY_LABEL))

        if not canDeployOnThisNode or gpuMemoryRequest > gpuMemory:
            continue
        
        for serviceTypeOnThisNode in serviceTypeOnThisNode_list:
            workloadLimitAfterDeployed = float(serviceSpec_dict[serviceTypeOnThisNode]['workAbility'][nodeDeployed]) / (len(serviceTypeOnThisNode_list)+1)
            if workloadLimitAfterDeployed < serviceSpec_dict[serviceTypeOnThisNode]['frequencyLimit'][0]:
                canDeployOnThisNode = False
                break
        if float(serviceSpec_dict[serviceType]['workAbility'][nodeDeployed]) / (len(serviceTypeOnThisNode_list)+1) < serviceSpec_dict[serviceType]['frequencyLimit'][0]:
            canDeployOnThisNode = False
        if canDeployOnThisNode:
            workloadLimitAfterDeployed_dict[nodeDeployed] = float(serviceSpec_dict[serviceType]['workAbility'][nodeDeployed]) / (len(serviceTypeOnThisNode_list)+1)
    
    if len(workloadLimitAfterDeployed_dict) == 0:
        return 'no enoungh computing resource'
    
    workloadLimit = max(workloadLimitAfterDeployed_dict.values())
    nodeName = next(iter(k for k, v in workloadLimitAfterDeployed_dict.items() if v == workloadLimit))

    # 計算在該節點上的服務數量並統計各類型服務之終端數量
    serviceTypeOnThisNode = 1
    serviceTypeOnThisNode += sum(1 for service in service_list if service['nodeName'] == nodeName)
    serviceConnection_dict = {}
    indexOfServiceOnDeployedNode = []
    for index, service in enumerate(service_list):
        if service['nodeName'] == nodeName: indexOfServiceOnDeployedNode.append(index)
        if service['serviceType'] not in serviceConnection_dict: serviceConnection_dict[service['serviceType']] = 0
        serviceConnection_dict[service['serviceType']] += int(service['currentConnection'])
        usedPort.add(int(service['hostPort']))

    adjustFrequencyServiceType_list = []
    # 檢查目前已存在之AI推論服務獲得的工作量是否能滿足傳送頻率下限
    for index in indexOfServiceOnDeployedNode:
        service_list[index]['workloadLimit'] = serviceSpec_dict[service_list[index]['serviceType']]['workAbility'][nodeName] / (len(indexOfServiceOnDeployedNode)+1) 
        originalService_list = copy.deepcopy(service_list)
        # 呼叫前端演算法並且把回傳結果存入service_list
        status, service_list = optimize(service_list[index]['serviceType'], serviceConnection_dict[service_list[index]['serviceType']], service_list)
        if status == 'fail':
            return 'no enoungh computing resource'
        if service_list != originalService_list:
            adjustFrequencyServiceType_list.append(service_list[index]['serviceType'])

    save_service_data(service_list)

    # 調整傳送頻率和配對關係
    for adjustFrequencyServiceType in adjustFrequencyServiceType_list:
        adjust_frequency(adjustFrequencyServiceType)

    for i in range(30500, 31000):
        if i not in usedPort:
            hostPort = i
            break
    
    resp = deploy_pod(serviceType,hostPort, nodeName)
    while resp is None:
        for i in range(hostPort+1, 31000):
            if i not in usedPort:
                hostPort = i
                break  
        resp = deploy_pod(serviceType,hostPort, nodeName)          
    logging.info(f"Function deploy_pod finish")

    podIP = resp.status.pod_ip
    hostIP = resp.status.host_ip
    nodeName = resp.spec.node_name
    podName = resp.metadata.name

    # 檢查Pod是否開始運行AI推論服務
    timeCounter = 0
    isPodReady = False
    while not isPodReady:
        pod = core_api.read_namespaced_pod(name = podName, namespace='default')
        for data in pod.status.conditions:
            if data.type == 'Ready' and data.status == 'True':
                logging.info(f"Pod {podName} is Ready")
                isPodReady = True
        if timeCounter == 12:
            logging.info(f"{podName} is still not Ready after 1 minutes")
            break
        if not isPodReady:
            time.sleep(5)
            timeCounter += 1

    service_list.append({
        "podIP" : str(podIP),
        "hostPort" : int(hostPort),
        "serviceType" : str(serviceType),
        "currentConnection" : 0,
        "nodeName" : nodeName,
        "hostIP" : str(hostIP),
        "frequencyLimit" : serviceSpec_dict[serviceType]['frequencyLimit'],
        "currentFrequency" : serviceSpec_dict[serviceType]['frequencyLimit'][0],
        "workloadLimit" : serviceSpec_dict[serviceType]['workAbility'][nodeName] / float(len(indexOfServiceOnDeployedNode)+1)
    })

    save_service_data(service_list)

    logging.info(f"deploy {serviceType} service successfully")
    return f"deploy {serviceType} service successfully"

def adjust_frequency(serviceType: str):

    podIPIndex_dict = {}

    service_list = load_service_data()
    subscription_list = load_subscription_data()

    for index, service in enumerate(service_list):
        if service['serviceType'] == serviceType:
            podIPIndex_dict[service['podIP']] = {}
            podIPIndex_dict[service['podIP']]['index'] = index
            podIPIndex_dict[service['podIP']]['currentConnection'] = service['currentConnection']
            podIPIndex_dict[service['podIP']]['currentFrequency'] = service['currentFrequency']
            podIPIndex_dict[service['podIP']]['nodeName'] = service['nodeName']

    reconfigureAgentIndex_list = []

    # 這個迴圈會先讓不用動的終端調整好頻率並收集需要移動的終端之index
    for index, subscription in enumerate(subscription_list):
        logging.debug(f"index {index} pod={subscription['podIP']} connection={podIPIndex_dict.get(subscription['podIP'], {}).get('currentConnection')}")
        # 如果該終端原本訂閱的Pod還有名額
        if subscription['podIP'] in podIPIndex_dict.keys() and podIPIndex_dict[subscription['podIP']]['currentConnection'] != 0 and subscription['serviceType'] == serviceType:
            podIPIndex_dict[subscription['podIP']]['currentConnection'] -=1
            body = {
                'servicename': serviceType,
                "ip": 'null',
                "port": 0,
                "frequency": service_list[podIPIndex_dict[subscription['podIP']]['index']]['currentFrequency']
            }
            communicate_with_agent(body,str(subscription['agentIP']), int(subscription['agentPort']))

        # 如果該終端原本訂閱的Pod沒有名額
        elif subscription['serviceType'] == serviceType:
            reconfigureAgentIndex_list.append(index)
            if subscription['podIP'] in podIPIndex_dict.keys(): del podIPIndex_dict[subscription['podIP']]

    for reconfigureAgentIndex in reconfigureAgentIndex_list:
        for key, value in podIPIndex_dict.items():
            if int(value['currentConnection']) != 0:
                value['currentConnection'] -=1
                body = {
                'servicename': serviceType,
                "ip": str(service_list[value['index']]['hostIP']),
                "port": int(service_list[value['index']]['hostPort']),
                "frequency": service_list[value['index']]['currentFrequency']
                }
                communicate_with_agent(body,str(subscription_list[reconfigureAgentIndex]['agentIP']), int(subscription_list[reconfigureAgentIndex]['agentPort']))
                subscription_list[reconfigureAgentIndex]['podIP'] = str(key)
                subscription_list[reconfigureAgentIndex]['nodeName'] = str(service_list[value['index']]['nodeName'])
                break
    
    # 更新subscription資料
    save_subscription_data(subscription_list)

    for key, value in podIPIndex_dict.items():
        if int(value['currentConnection']) !=0:
            logging.info(f"Function adjust_frequency() adjust frequency of {serviceType} and return {value['index']}")
            return value['index']

    logging.info(f"Function adjust_frequency() adjust frequency of {serviceType}")
    return None

def get_node_ip(node_name: str) -> str:
    try:
        config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {e}")
        raise

    core_api = client.CoreV1Api()

    try:
        # 獲取指定節點的資訊
        node = core_api.read_node(name=node_name)
        
        # 提取節點的 IP 地址，通常是節點地址列表中的 InternalIP
        for address in node.status.addresses:
            if address.type == "InternalIP":
                return address.address
        
        # 如果沒有找到 InternalIP，就返回 "未找到" 的消息
        print("InternalIP not found")
        return "Error"
    
    except client.exceptions.ApiException as e:
        print(f"Exception when calling CoreV1Api->read_node: {e}")
        return "Error"

def curl_health_check(ip: str):
    url = f"http://{ip}:10248/healthz"
    try:
        # 發送 GET 請求，設置超時為 1 秒
        response = requests.get(url, timeout=1)
        
        # 檢查回應狀態碼是否為 200 (OK)
        if response.status_code == 200:
            print(f"Health check successful for {url}")
            print("Response Status Code:", response.status_code)
            print("Response Body:", response.text)
            return response.text
        else:
            return f"Health check failed for {url}. Status Code: {response.status_code}"
    
    except requests.exceptions.Timeout:
        return f"Request to {url} timed out. The URL may not exist."
    except requests.exceptions.RequestException as e:
        return f"An error occurred while trying to reach {url}: {e}"
 
def deploy_pod(service_type,hostPort, node_name):
    try:
        config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {e}")
        logging.error(f"Error loading kubeconfig: {e}")
        raise

    core_api = client.CoreV1Api()

    # 讀取要部署的Pod的YAML文件
    try:
        with open(f"service_yaml/{service_type}.yaml") as f:
            dep = yaml.safe_load(f)
    except Exception as e:
        print("Service Type YAML file not found")
        logging.error("Service Type YAML file not found")
        raise
    # 生成唯一的Pod名稱
    unique_name = f"{service_type}-{str(node_name)}-{str(hostPort)}"

    # 更新Pod名稱和hostPort
    dep['metadata']['name'] = unique_name
    dep['spec']['containers'][0]['ports'][0]['hostPort'] = hostPort

    # 設置nodeSelector以指定部署節點
    dep['spec']['nodeSelector'] = {'kubernetes.io/hostname': node_name}

    # **檢查是否有同名的 Pod 並確保它不是在刪除中**
    if is_pod_terminating(core_api, unique_name):
        logging.warning(f"Pod {unique_name} is terminating, changing hostPort...")
        return None  # 讓外部程式重新選擇 hostPort
    
    # 部署Pod
    try:
        resp = core_api.create_namespaced_pod(body=dep, namespace='default')
        print(f"Pod {resp.metadata.name} created.")
        logging.info(f"Send the request of deploying Pod {resp.metadata.name}.")
    except ApiException as e:
        print(f"Exception when deploying Pod: {e}")
        logging.error(f"Exception when deploying Pod: {e}")
        raise

    while True:
        resp = core_api.read_namespaced_pod(name=unique_name, namespace='default')
        if resp.spec.node_name and resp.status.pod_ip and resp.status.host_ip:
            print(f"Pod {unique_name} (IP:{resp.status.pod_ip}) is scheduled to node {resp.spec.node_name} (IP:{resp.status.host_ip}).")
            break
        time.sleep(0.5)  # 等待0.5秒再檢查一次
    return resp

def communicate_with_agent(data: dict, agent_ip: str, agent_port: int):
    url = f"http://{agent_ip}:{agent_port}/servicechange"
    try:
        response = requests.post(url, data=json.dumps(data))
        logging.info(f"communicate with Agent {agent_ip} {agent_port}, body = {data}")
        return response.status_code, response.text
    except requests.exceptions.RequestException as e:
        return None, str(e)

def delete_pod(pod_name, namespace='default'):

    try:
        config.load_incluster_config() if IN_CLUSTER else config.load_kube_config()
    except Exception as e:
        print(f"Error loading kubeconfig: {e}")
        logging.error(f"Error loading kubeconfig: {e}")
        raise

    # 建立 API 客戶端
    core_api = client.CoreV1Api()

    try:
        # 刪除指定 namespace 中的 Pod
        core_api.delete_namespaced_pod(name=pod_name, namespace=namespace)
        print(f"Pod {pod_name} deleted successfully in namespace {namespace}.")
    except ApiException as e:
        if e.status == 404:
            print(f"Pod {pod_name} not found in namespace {namespace}.")
        else:
            print(f"Failed to delete Pod: {e}")

def node_status_sync(node_name_list: List[str]):
    node_health_status = {}

    # 使用 ThreadPoolExecutor 平行處理健康檢查
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # 用於儲存未來結果的字典
        future_to_node = {}
        
        for node_name in node_name_list:
            # 呼叫 get_node_ip 取得節點 IP
            ip = get_node_ip(node_name)
            
            if ip != "Error":
                # 提交 curl_health_check 到執行緒池，並將 node_name 和 future 綁定
                future = executor.submit(curl_health_check, ip)
                future_to_node[future] = node_name
            else:
                # 如果未能取得 IP，視為 unhealthy
                node_health_status[node_name] = "unhealthy"

        # 收集所有已完成的健康檢查
        for future in concurrent.futures.as_completed(future_to_node):
            node_name = future_to_node[future]
            try:
                # 獲取健康檢查結果
                health_status = future.result()
                
                # 根據回傳值來決定健康狀態
                if health_status.strip().lower() == 'ok':
                    node_health_status[node_name] = "healthy"
                else:
                    node_health_status[node_name] = "unhealthy"
                    
            except Exception as e:
                # 捕捉任何執行過程中的例外情況
                node_health_status[node_name] = "unhealthy"
    try:
        save_nodestatus_data(node_health_status)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to write to node_status file")
    # 將結果轉換為 JSON 格式並返回
    return json.dumps(node_health_status, indent=4)

def is_pod_terminating(core_api, pod_name, namespace="default"):
    """
    Check if pod is deleting
    """
    try:
        resp = core_api.read_namespaced_pod(name=pod_name, namespace=namespace)
        if resp.metadata.deletion_timestamp:  # 檢查 Pod 是否標記為刪除中
            return True
    except ApiException as e:
        if e.status == 404:  # Pod 不存在，可能已經被刪除
            return False
        logging.error(f"Error checking pod status: {e}")
    return False