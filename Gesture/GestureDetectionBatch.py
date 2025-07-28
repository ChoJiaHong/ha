import json
import base64
import threading
import queue
from concurrent import futures
from grpc_health.v1 import health_pb2_grpc, health_pb2
import grpc
import gesture_pb2
import gesture_pb2_grpc
import time
import cv2
import numpy as np
from datetime import datetime
import traceback

from vision.ssd.mobilenetv1_ssd import create_mobilenetv1_ssd, create_mobilenetv1_ssd_predictor
from vision.utils.misc import Timer
from config import settings

# 模型與預測器
class_names = [name.strip() for name in open(settings.label_path).readlines()]
net = create_mobilenetv1_ssd(len(class_names), is_test=True)
net.load(settings.weights)
predictor = create_mobilenetv1_ssd_predictor(net, candidate_size=200)

# queue 與設定
request_queue = queue.Queue()
response_map = {}
BATCH_SIZE = 5
MAX_WAIT_TIME = 0.05

frame_index = 0
timer = Timer()

class HealthServicer(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)

def batch_worker():
    global frame_index
    while True:
        batch = []
        ids = []
        timestamps = []
        start_time = time.time()

        while len(batch) < BATCH_SIZE and (time.time() - start_time) < MAX_WAIT_TIME:
            try:
                req_id, image_bytes = request_queue.get(timeout=MAX_WAIT_TIME)
                nparr = np.frombuffer(image_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                batch.append(img)
                ids.append(req_id)
                timestamps.append(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            except queue.Empty:
                break

        if not batch:
            continue

        results = predictor.predict_batch(batch, top_k=settings.top_k, prob_threshold=settings.conf_thres)

        for i, (boxes, labels, probs) in enumerate(results):
            frame_index += 1
            text = {'Left': "", 'Right': ""}
            for j in range(boxes.size(0)):
                label_name = class_names[labels[j]]
                digit = label_name.split("_")[-1]
                text["Left"] = digit
                text["Right"] = digit

            action = json.dumps(text)
            response_map[ids[i]] = gesture_pb2.RecognitionReply(
                frame_index=frame_index,
                timestamp=timestamps[i],
                action=action
            )

# 啟動 batch 執行緒
threading.Thread(target=batch_worker, daemon=True).start()

class GestureRecognitionService(gesture_pb2_grpc.GestureRecognitionServicer):
    def Recognition(self, request, context):
        req_id = str(time.time()) + "_" + str(threading.get_ident())
        image_bytes = base64.b64decode(request.image)
        request_queue.put((req_id, image_bytes))

        while True:
            if req_id in response_map:
                return response_map.pop(req_id)
            time.sleep(0.005)

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    gesture_pb2_grpc.add_GestureRecognitionServicer_to_server(GestureRecognitionService(), server)
    server.add_insecure_port("[::]:" + settings.gRPC_port)
    server.start()
    print("Server started on port", settings.gRPC_port)
    server.wait_for_termination()

if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        print("Gesture gRPC server stop!")
