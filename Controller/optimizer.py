def optimize(servicetype: str, agentcount: int, servicelist: list) -> tuple[str, list]:
    """
    Optimize the agent's transmission rate and the allocation.

    Parameters
    ----------
    servicetype : str
        the type of the service
    agentcount : int
        number of agent that needs to be optimized
    servicelist: list
        a list of informations of all service instances

    Returns
    -------
    status : str
        the optimization is "success" or "fail"
    servicelist : list
        a list of updated informations of all service instances
    """
    
    status = "success"
    hasdistributed = 0      # number of agent that has been distributed

    # 儲存原始順序
    for i, instance in enumerate(servicelist):
        instance["originalIndex"] = i

    for instance in servicelist:
        # clear all the current connection to redistribute
        if instance["serviceType"] == servicetype:
            instance["currentConnection"] = 0
        # add a field called remainWorkload
        instance["remainWorkload"] = instance["workloadLimit"] - instance["currentConnection"] * instance["frequencyLimit"][0]
        # add a field called predFreq
        # represent the freq when a new agent is added
        instance["predFreq"] = instance["workloadLimit"] / (instance["currentConnection"] + 1)
    # sort by remainWorkload descending
    servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)

    idx = 0
    while hasdistributed < agentcount and idx < len(servicelist):
        if servicelist[idx]["serviceType"] == servicetype:
            if servicelist[idx]["remainWorkload"] >= servicelist[idx]["frequencyLimit"][0]:
                # can distribute as default transmission rate
                servicelist[idx]["currentConnection"] += 1
                servicelist[idx]["remainWorkload"] -= servicelist[idx]["frequencyLimit"][0]
                servicelist[idx]["currentFrequency"] = servicelist[idx]["frequencyLimit"][0]
                servicelist[idx]["predFreq"] = servicelist[idx]["workloadLimit"] / (servicelist[idx]["currentConnection"] + 1)
                hasdistributed += 1
                servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)
                idx = 0
            else:
                break
        else:
            # wrong service type, skip
            idx += 1
            continue
    # if no agent is distributed, there is no instance of the service type
    if hasdistributed == 0:
        for instance in servicelist:
            del instance["remainWorkload"]
            del instance["predFreq"]
            del instance["originalIndex"]
            status = "fail"
        return status, servicelist

    # all instance is full, cannot add a agent with default transmission rate
    idx = 0
    while hasdistributed < agentcount and idx < len(servicelist):
        servicelist = sorted(servicelist, key=lambda x: x["predFreq"], reverse=True)
        if servicelist[idx]["serviceType"] == servicetype:
            # let agent join the instance which has the most predFreq
            servicelist[idx]["currentConnection"] += 1
            servicelist[idx]["currentFrequency"] = servicelist[idx]["workloadLimit"] / servicelist[idx]["currentConnection"]
            servicelist[idx]["remainWorkload"] = 0

            # the freqency is under minimum FPS fli
            if servicelist[idx]["currentFrequency"] < servicelist[idx]["frequencyLimit"][1]:
                status = "fail"

            servicelist[idx]["predFreq"] = servicelist[idx]["workloadLimit"] / (servicelist[idx]["currentConnection"] + 1)
            hasdistributed += 1
            servicelist = sorted(servicelist, key=lambda x: x["predFreq"], reverse=True)
            idx = 0
        else:
            # wrong service type, skip
            idx += 1
            continue

    for instance in servicelist:
        del instance["remainWorkload"]
        del instance["predFreq"]

    # 恢復原本順序並移除標記欄位
    servicelist = sorted(servicelist, key=lambda x: x["originalIndex"])
    for instance in servicelist:
        del instance["originalIndex"]
        
    return status, servicelist

def uniform(servicetype: str, agentcount: int, servicelist: list) -> tuple[str, list]:
    """
    default transmission rate, agents are uniformly distributed to all service instances

    Parameters
    ----------
    servicetype : str
        the type of the service
    agentcount : int
        number of agent that needs to be distributed
    servicelist: list
        a list of informations of all service instances

    Returns
    -------
    status : str
        the distribution is "success" or "fail"
    servicelist : list
        a list of updated informations of all service instances
    """
    status = "success"
    hasdistributed = 0      # number of agent that has been distributed

    for instance in servicelist:
        if instance["serviceType"] == servicetype:
            # clear all connection
            instance["currentConnection"] = 0
            # set the frequency to default
            instance["currentFrequency"] = instance["frequencyLimit"][0]
    while hasdistributed < agentcount:
        for instance in servicelist:
            if hasdistributed == agentcount:
                break
            if instance["serviceType"] == servicetype:
                instance["currentConnection"] += 1
                hasdistributed += 1
    return status, servicelist 

def most_remaining(servicetype: str, agentcount: int, servicelist: list) -> tuple[str, list]:
    """
    default transmission rate, distribute the agent to the service instance that has most remaining capacity

    Parameters
    ----------
    servicetype : str
        the type of the service
    agentcount : int
        number of agent that needs to be distributed
    servicelist: list
        a list of informations of all service instances

    Returns
    -------
    status : str
        the distribution is "success" or "fail"
    servicelist : list
        a list of updated informations of all service instances
    """
    status = "success"
    hasdistributed = 0      # number of agent that has been distributed

    for instance in servicelist:
        # clear all the current connection to redistribute
        if instance["serviceType"] == servicetype:
            instance["currentConnection"] = 0
            # set the frequency to default
            instance["currentFrequency"] = instance["frequencyLimit"][0]
        # add a field called remainWorkload
        instance["remainWorkload"] = instance["workloadLimit"] - instance["currentConnection"] * instance["frequencyLimit"][0]
    servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)

    idx = 0
    while hasdistributed < agentcount:
        if servicelist[idx]["serviceType"] == servicetype:
            servicelist[idx]["currentConnection"] += 1
            hasdistributed += 1
            servicelist[idx]["remainWorkload"] -= instance["frequencyLimit"][0]
            servicelist = sorted(servicelist, key=lambda x: x["remainWorkload"], reverse=True)
            idx = 0
        else:
            idx += 1
    for instance in servicelist:
        del instance["remainWorkload"]
    return status, servicelist

if __name__ == "__main__":
    service = [{
            "podIP" : "ip1",
            "hostPort" : 1,
            "serviceType" : "object",
            "currentConnection" : 10,
            "nodeName" : "nodename",
            "hostIP" : "hostip",
            "frequencyLimit" : [5,3],
            "currentFrequency" : 1,
            "workloadLimit" : 5
        },{
            "podIP" : "ip2",
            "hostPort" : 2,
            "serviceType" : "object",
            "currentConnection" : 20,
            "nodeName" : "nodename",
            "hostIP" : "hostip",
            "frequencyLimit" : [5,3],
            "currentFrequency" : 1,
            "workloadLimit" : 50
        }]

    status, servicelist = optimize("object", 101, service)

    print(servicelist)
    print(status)