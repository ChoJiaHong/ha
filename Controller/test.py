def adjust_frequency(serviceType: str):

    podIPIndex_dict = {}

    subscription_list = [{'agentIP': '10.52.52.125', 'agentPort': 10000, 'podIP': '10.244.2.31', 'serviceType': 'pose', 'nodeName': 'workergpu2'}, {'agentIP': '10.52.52.125', 'agentPort': 10000, 'podIP': '10.244.1.164', 'serviceType': 'gesture', 'nodeName': 'workergpu'}, {'agentIP': '10.52.52.58', 'agentPort': 10000, 'podIP': '10.244.2.31', 'serviceType': 'pose', 'nodeName': 'workergpu2'}, {'agentIP': '10.52.52.58', 'agentPort': 10000, 'podIP': '10.244.1.164', 'serviceType': 'gesture', 'nodeName': 'workergpu'}, {'agentIP': '10.52.52.59', 'agentPort': 10000, 'podIP': '10.244.2.31', 'serviceType': 'pose', 'nodeName': 'workergpu2'}, {'agentIP': '10.52.52.59', 'agentPort': 10000, 'podIP': '10.244.1.164', 'serviceType': 'gesture', 'nodeName': 'workergpu'}, {'agentIP': '10.52.52.125', 'agentPort': 10001, 'podIP': '10.244.2.31', 'serviceType': 'pose', 'nodeName': 'workergpu2'}, {'agentIP': '10.52.52.125', 'agentPort': 10001, 'podIP': '10.244.1.164', 'serviceType': 'gesture', 'nodeName': 'workergpu'}, {'agentIP': '10.52.52.58', 'agentPort': 10001, 'podIP': '10.244.1.165', 'serviceType': 'pose', 'nodeName': 'workergpu'}, {'agentIP': '10.52.52.59', 'agentPort': 10001, 'podIP': '10.244.2.31', 'serviceType': 'pose', 'nodeName': 'workergpu2'}]

    service_list = [{'podIP': '10.244.2.31', 'hostPort': 30501, 'serviceType': 'pose', 'currentConnection': 4, 'nodeName': 'workergpu2', 'hostIP': '10.52.52.26', 'frequencyLimit': [20, 10], 'currentFrequency': 10.0, 'workloadLimit': 40.0}, {'podIP': '10.244.1.164', 'hostPort': 30500, 'serviceType': 'gesture', 'currentConnection': 4, 'nodeName': 'workergpu', 'hostIP': '10.52.52.25', 'frequencyLimit': [30, 15], 'currentFrequency': 22.5, 'workloadLimit': 90.0}, {'podIP': '10.244.1.165', 'hostPort': 30502, 'serviceType': 'pose', 'currentConnection': 2, 'nodeName': 'workergpu', 'hostIP': '10.52.52.25', 'frequencyLimit': [20, 10], 'currentFrequency': 15.0, 'workloadLimit': 30.0}]
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
        print(f"index {index} pod={subscription['podIP']} connection={podIPIndex_dict.get(subscription['podIP'], {}).get('currentConnection')}")
        # 如果該終端原本訂閱的Pod還有名額
        if subscription['podIP'] in podIPIndex_dict.keys() and podIPIndex_dict[subscription['podIP']]['currentConnection'] != 0 and subscription['serviceType'] == serviceType:
            podIPIndex_dict[subscription['podIP']]['currentConnection'] -=1
            body = {
                'servicename': serviceType,
                "ip": 'null',
                "port": 0,
                "frequency": service_list[podIPIndex_dict[subscription['podIP']]['index']]['currentFrequency']
            }
            print("有溝通")
        # 如果該終端原本訂閱的Pod沒有名額
        elif subscription['serviceType'] == serviceType:
            reconfigureAgentIndex_list.append(index)
            if subscription['podIP'] in podIPIndex_dict.keys(): del podIPIndex_dict[subscription['podIP']]

    print(reconfigureAgentIndex_list)
    print(podIPIndex_dict)
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
                subscription_list[reconfigureAgentIndex]['podIP'] = str(key)
                subscription_list[reconfigureAgentIndex]['nodeName'] = str(service_list[value['index']]['nodeName'])
                break


    for key, value in podIPIndex_dict.items():
        if int(value['currentConnection']) !=0:
            print(f"Function adjust_frequency() adjust frequency of {serviceType} and return {value['index']}")
            return value['index']

    print(f"Function adjust_frequency() adjust frequency of {serviceType}")
    return None

adjust_frequency("pose")