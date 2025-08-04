import asyncio
import logging
import os
import threading
import time
from fastapi import FastAPI, Form, Request
import requests
import uvicorn
import paramiko
import json
import sys
import websockets

# python AgentManager_websocket.py number_of_agenthost agenthost1_ip agenthost1_account agenthost1_passward agenthost2_ip genthost2_account agenthost2_passward
# e.g. python AgentManager_websocket.py 2 10.52.52.58 user58 user 10.52.52.59 user59 user
Agent_Host_Number = int(sys.argv[1])

current_agent_host = -1

Agent_Host = []
Agent_Host_ACCOUNT = []
Agent_Host_PASSWORD = []

for i in range(Agent_Host_Number):
    Agent_Host.append(sys.argv[3 * i + 2])
    Agent_Host_ACCOUNT.append(sys.argv[3 * i + 3])
    Agent_Host_PASSWORD.append(sys.argv[3 * i + 4])

port = 8888
websocket_port = 50051

Service = ["Pose", "Gesture"]

incluster = True

if incluster:
    ControllerIP = "controller-service"
    ControllerPort = 80
else:
    ControllerIP = "10.52.52.126"
    ControllerPort = 30004

log_dir = "logs"
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

logging.basicConfig(filename=os.path.join(log_dir, "AgentManager.log"),
                    format='%(asctime)s %(levelname)s: %(message)s',
                    level=logging.INFO)

app = FastAPI()

@app.middleware("http")
async def log_requests(request: Request, call_next):
    log_data = {
        "client_host": request.client.host,
        "client_port": request.client.port,
        "method": request.method,
        "url": str(request.url),
    }

    logging.info(f"HTTP Request: {log_data}")

    response = await call_next(request)
    return response

@app.post("/subscribe")
async def agent(request: Request):
    client_host = request.client.host
    client_port = request.client.port

    #call a function to create a agent on agent host
    ip, port, websocket_port = create_agent()

    #store the bind information of agent and client in AR_Agent.json
    store_information(client_host, ip, port, websocket_port)

    print(ip)
    print(port)
    print(websocket_port)

    #return the ip, port of the agent that just created
    return {"IP": ip, "Port": port, "WebsocketPort": websocket_port}

@app.post("/agentfail")
async def agentfail(request: Request):
    #todo
    #find the corresponding agent
    failed_agent, failed_agentport, failed_agentwebsocketport = find_pair_information(request.client.host)
    if failed_agent == None or failed_agentport == None or failed_agentwebsocketport == None:
        logging.error(f"Agent not found for client: {request.client.host}")
        return {"status": "500", "message": "agent not found"}


    #get a new agent information, need to tell controller who's the successor
    new_agent_port, new_agent_websocketport = generate_agent_information()
    #call controller to get agent information
    body = {
        "old_ip": failed_agent,
        "old_port": failed_agentport,
        "new_ip": Agent_Host,
        "new_port": new_agent_port
    }
    response = requests.post(f'http://{ControllerIP}:{ControllerPort}/agentfail', json.dumps(body))
    if response.status_code != 200:
        logging.error("Failed to get result from controller")
        return{"status": "500", "message": "fail getting result from controller"}
    response = response.json()
    logging.info(f"got old information from controller: {response}")

    try:
        pose_ip = "0"
        pose_port = 0
        pose_freq = 0
        ges_ip = "0"
        ges_port = 0
        ges_freq = 0

        for service in response:
            servicetype = service['ServiceType']
            if servicetype == 'pose':
                pose_ip = service['IP']
                pose_port = service['Port']
                pose_freq = service['Frequency']
            elif servicetype == 'gesture':
                ges_ip = service['IP']
                ges_port = service['Port']
                ges_freq = service['Frequency']
        # pose_ip = response[0].get("IP")
        # pose_port = response[0].get("Port")
        # pose_freq = response[0].get("Frequency")
        # ges_ip = response[1].get("IP")
        # ges_port = response[1].get("Port")
        # ges_freq = response[1].get("Frequency")
    except Exception:
        logging.error(f"Error parsing response: {response}")
        print(response)

    #call a function to create a agent on agent host
    ip, port, websocket_port = create_agent(pose_IP=pose_ip, pose_Port=pose_port, pose_Freq=pose_freq, ges_IP=ges_ip, ges_Port=ges_port, ges_Freq=ges_freq, newport=new_agent_port, newwebsocketport=new_agent_websocketport)

    #store the bind information of the new agent and client
    store_information(request.client.host, ip, port, websocket_port)

    return {"status": "200", "message": "OK"}

@app.get("/newagent")
async def newagent(request: Request):
    #find the pair relationship of client and agent
    ip , port, websocketport = find_pair_information(request.client.host)
    if ip == None or port == None or websocketport == None:
        ip = ""
        port = 0
        websocketport = 0

    logging.info(f"New agent info: IP={ip}, Port={port}, WebsocketPort={websocketport}")
    #return the corresponding agent ip and port
    body = {
        "IP": ip,
        "Port": port,
        "WebsocketPort": websocketport
    }
    return {"IP": ip, "Port": port, "WebsocketPort": websocketport}

def run_server():
    #the IP and Port to run Agent Manager
    #needs to modify
    logging.info("HTTP server started on 0.0.0.0:" + str(port))
    uvicorn.run(app, host="0.0.0.0", port= port)

'''
pose_IP : ip of pose detection service
pose_Port : port of pose detection service
pose_Freq : sending freqency of pose detection service
ges_IP : ip of gesture detection service
ges_Port : port of gesture detection service
ges_Freq : sending freqency of gesture detection service
newport : a agent port that is already created, no need to create again
newwebsocketport : a agent websocket port that is already created, no need to create again
'''
def create_agent(Host: int, pose_IP="0", pose_Port=0, pose_Freq=0, ges_IP="0", ges_Port=0, ges_Freq=0, newport=0, newwebsocketport=0):
    #optional args old informations


    #get a unique agent information
    if newport == 0 or newwebsocketport == 0:
        newport, newwebsocketport = generate_agent_information()

    #connect to agent host and create agent by command
    ssh = paramiko.SSHClient()

    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    ssh.connect(hostname=Agent_Host[Host], username=str(Agent_Host_ACCOUNT[Host]), password=str(Agent_Host_PASSWORD[Host]))

    logging.info(f"connected to Agent Host {Agent_Host[Host]}")

    #python Agent_websocket.py {IP} {Port} {websocket_port} {ip of pose det} {port of pose det} {sending freq of pose det} {ip of gesture det} {port of gesture det} {sending freq of gesture det}

    print("before command")
    #docker run -d --rm -p 8888:8888 -p 8889:8889 wlin90/agent_websocket:latest 0.0.0.0 8888 8889
    #print(f"nohup python3 Agent_websocket.py {Agent_Host} {newport} {newwebsocketport} > /dev/null 2>&1 &")
    #stdin, stdout, stderr = ssh.exec_command(f"nohup python3 Agent_websocket.py {Agent_Host} {port} {websocket_port} > /dev/null 2>&1 &")
    command = f"docker run -d --rm -v /home/logs:/app/logs -p {newport}:{newport} -p {newwebsocketport}:{newwebsocketport} wlin90/agent_websocket:1.0 {Agent_Host[Host]} {newport} {newwebsocketport}"
    command += f" {pose_IP} {pose_Port} {pose_Freq} {ges_IP} {ges_Port} {ges_Freq}"
    print(command)
    stdin, stdout, stderr = ssh.exec_command(command)
    print("after command")
    logging.info(f"executed command on Agent Host {Agent_Host[Host]} {command}")

    time.sleep(2)

    ssh.close()

    return Agent_Host[Host], newport, newwebsocketport

#generate a agent host, a new agent port and websocket port
def generate_agent_information():
    global current_agent_host
    global Agent_Host_Number
    global port
    global websocket_port

    current_agent_host = (current_agent_host + 1) % Agent_Host_Number
    port += 1
    websocket_port += 1
    return current_agent_host, port - 1, websocket_port - 1

def store_information(ar: str, agent: str, agentport: int, agentwebsocketport: int):
    logging.info(f"store info for AR: {ar} and agent: {agent} {agentport} {agentwebsocketport}")
    if os.path.exists('AR_Agent.json'):
        with open('AR_Agent.json', 'r') as json_file:
            data_list = json.load(json_file)
    else:
        data_list = []

    for data in data_list:
        if data["AR"] == ar:
            data_list.remove(data)

    newpair = {"AR": ar, "Agent": agent, "AgentPort": agentport, "AgentWebsocketPort": agentwebsocketport}

    data_list.append(newpair)

    with open('AR_Agent.json', 'w') as json_file:
        json.dump(data_list, json_file)

def find_pair_information(ar: str):
    logging.info(f"find the agent of AR ({ar})")
    if os.path.exists('AR_Agent.json'):
        with open('AR_Agent.json', 'r') as json_file:
            data_list = json.load(json_file)
    else:
        logging.error(f"Agent not found for {ar}")
        return None, None, None

    for data in data_list:
        if data["AR"] == ar:
            logging.info(f"Agent found, ip: {data['Agent']}, port: {data['AgentPort']}, websocketport: {data['AgentWebsocketPort']}")
            return data["Agent"], data["AgentPort"], data["AgentWebsocketPort"]
    logging.error(f"Agent not found for {ar}")
    return None, None, None

def subscribe_services(host:int, port: int, servicename: str):
    body = {
        "ip" : str(Agent_Host[host]),
        "port" : port,
        "serviceType" : servicename
    }
    response = requests.post(f'http://{ControllerIP}:{ControllerPort}/subscribe', data = json.dumps(body))
    response = response.json()
    logging.info(f"subscribed {servicename} service for new agent: {response}")
    return response.get('IP'), response.get('Port'), response.get('Frequency')

# 客戶端連接後的處理
async def handle_client(websocket, path):
    print(f"Client connected from {path}")
    client_ip, client_port = websocket.remote_address
    logging.info(f"WebSocket Client connected from {client_ip}:{client_port}")
    print(f"client ip = {client_ip}, port = {client_port}")
    #todo
    #get agent host and generate two port
    host, new_agent_port, new_agent_websocketport = generate_agent_information()
    print(f"got new agent info with ip {Agent_Host[host]} port {new_agent_port} and websocketport {new_agent_websocketport}")
    logging.info(f"New agent generated for WebSocket client: IP={Agent_Host[host]} Port={new_agent_port}, WebsocketPort={new_agent_websocketport}")
    #subscribe services for client from controller
    pose_ip, pose_port, pose_freq = subscribe_services(host, new_agent_port, "pose")
    ges_ip, ges_port, ges_freq = subscribe_services(host, new_agent_port, "gesture")
    print("subscribed service")

    #create a agent by the information from controller, need to add gesture
    create_agent(Host=host, pose_IP=pose_ip, pose_Port= pose_port, pose_Freq=pose_freq, ges_IP=ges_ip, ges_Port=ges_port, ges_Freq=ges_freq, newport=new_agent_port, newwebsocketport=new_agent_websocketport)
    print("created agent")
    #store the pair information of client and agent
    store_information(client_ip, Agent_Host[host], new_agent_port, new_agent_websocketport)
    #return the agent information
    response_data = {
        "host": Agent_Host[host],
        "port": new_agent_port,
        "websocket_port": new_agent_websocketport
    }
    # 將數據轉換為 JSON 格式
    #response_json = json.dumps(response_data)

    await websocket.send(f"{Agent_Host[host]} {new_agent_port} {new_agent_websocketport}")

    try:
        # 持續等待來自客戶端的消息
        async for message in websocket:
            #print(f"Received message from client: {message}")

            # 回應給客戶端
            response = f"Server received your message: {message}"
            #await websocket.send(response)
    except websockets.ConnectionClosed:
        print("Client disconnected")

# 啟動 WebSocket 伺服器
async def start_server():
    server = await websockets.serve(handle_client, "0.0.0.0", websocket_port)
    print("WebSocket server started on ws://0.0.0.0:" + str(websocket_port))
    logging.info("WebSocket server started on ws://0.0.0.0:" + str(websocket_port))
    await server.wait_closed()

if __name__ == "__main__":
    app.debug = False
    #run_server()
    threading.Thread(target = run_server).start()

    asyncio.get_event_loop().run_until_complete(start_server())
    asyncio.get_event_loop().run_forever()