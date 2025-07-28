import json
import base64
import threading
import queue
import time
import grpc
from concurrent import futures
from datetime import datetime

import cv2
import numpy as np

from config import settings
from vision.ssd.mobilenetv1_ssd import create_mobilenetv1_ssd, create_mobilenetv1_ssd_predictor
from vision.utils.misc import Timer

import gesture_pb2
import gesture_pb2_grpc
from grpc_health.v1 import health_pb2_grpc, health_pb2


class HealthServicer(health_pb2_grpc.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(status=health_pb2.HealthCheckResponse.SERVING)


class RequestWrapper:
    def __init__(self, image_data):
        self.image_data = image_data
        self.result_queue = queue.Queue()


class GestureDetectionWorker:
    def __init__(self, worker_id):
        self.worker_id = worker_id
        self.class_names = [name.strip() for name in open(settings.label_path).readlines()]
        self.net = create_mobilenetv1_ssd(len(self.class_names), is_test=True)
        self.net.load(settings.weights)
        self.predictor = create_mobilenetv1_ssd_predictor(self.net, candidate_size=200)
        self.queue = queue.Queue()
        self.batch_size = settings.batch_size
        self.queue_timeout = settings.queue_timeout
        self.frame_index = 0
        threading.Thread(target=self._batch_worker, daemon=True).start()

    def handle_request(self, image_data):
        wrapper = RequestWrapper(image_data)
        self.queue.put(wrapper)
        return wrapper.result_queue.get()

    def _batch_worker(self):
        while True:
            batch_frames = []
            wrappers = []
            timestamps = []
            start_time = time.time()

            while len(batch_frames) < self.batch_size and (time.time() - start_time) < self.queue_timeout:
                try:
                    wrapper = self.queue.get(timeout=0.01)
                    nparr = np.frombuffer(wrapper.image_data, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    batch_frames.append(img)
                    wrappers.append(wrapper)
                    timestamps.append(datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
                except queue.Empty:
                    pass

            if not batch_frames:
                continue

            results = self.predictor.predict_batch(batch_frames, top_k=settings.top_k, prob_threshold=settings.conf_thres)

            for i, (boxes, labels, probs) in enumerate(results):
                self.frame_index += 1
                text = {"Left": "", "Right": ""}

                for j in range(boxes.size(0)):
                    label_name = self.class_names[labels[j]]
                    digit = label_name.split("_")[-1]
                    text["Left"] = digit
                    text["Right"] = digit

                reply = gesture_pb2.RecognitionReply(
                    frame_index=self.frame_index,
                    timestamp=timestamps[i],
                    action=json.dumps(text)
                )
                wrappers[i].result_queue.put(reply)


class GestureRecognitionService(gesture_pb2_grpc.GestureRecognitionServicer):
    def __init__(self):
        self.num_workers = settings.num_workers
        self.workers = [GestureDetectionWorker(i) for i in range(self.num_workers)]
        self.next_worker = 0
        self.lock = threading.Lock()

    def Recognition(self, request, context):
        with self.lock:
            worker = self.workers[self.next_worker]
            self.next_worker = (self.next_worker + 1) % self.num_workers
        image_bytes = base64.b64decode(request.image)
        return worker.handle_request(image_bytes)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    gesture_pb2_grpc.add_GestureRecognitionServicer_to_server(GestureRecognitionService(), server)
    server.add_insecure_port("[::]:" + settings.gRPC_port)
    server.start()
    print("Gesture gRPC server started on port", settings.gRPC_port)
    server.wait_for_termination()


if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        print("Gesture gRPC server stopped")
