from flask import Flask, Response
import subprocess
import os

app = Flask(__name__)

def get_gpu_utilization():
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"]
        ).decode().strip()
        return float(output)
    except Exception:
        return -1

@app.route("/metrics")
def metrics():
    util = get_gpu_utilization()
    pod_name = os.environ.get("POD_NAME", "unknown")
    node_name = os.environ.get("NODE_NAME", "unknown")

    return Response(
        f'pod_gpu_utilization{{pod="{pod_name}", node="{node_name}"}} {util}\n',
        mimetype="text/plain"
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9101)
