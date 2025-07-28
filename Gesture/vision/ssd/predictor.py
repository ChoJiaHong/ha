import torch
from ..utils import box_utils
from .data_preprocessing import PredictionTransform
from ..utils.misc import Timer

class Predictor:
    def __init__(self, net, size, mean=0.0, std=1.0, nms_method=None,
                 iou_threshold=0.45, filter_threshold=0.01, candidate_size=200, sigma=0.5, device=None):
        self.net = net
        self.transform = PredictionTransform(size, mean, std)
        self.iou_threshold = iou_threshold
        self.filter_threshold = filter_threshold
        self.candidate_size = candidate_size
        self.nms_method = nms_method
        self.sigma = sigma
        self.device = device if device else torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.net.to(self.device)
        self.net.eval()
        self.timer = Timer()

    def predict(self, image, top_k=-1, prob_threshold=None):
        cpu_device = torch.device("cpu")
        height, width, _ = image.shape
        image = self.transform(image)
        images = image.unsqueeze(0).to(self.device)

        with torch.no_grad():
            self.timer.start("default")
            scores, boxes = self.net.forward(images)
            print("Inference time: ", self.timer.end("default"))

        return self._postprocess(scores[0], boxes[0], width, height, top_k, prob_threshold or self.filter_threshold)

    def predict_batch(self, image_list, top_k=-1, prob_threshold=None):
        cpu_device = torch.device("cpu")
        heights = [img.shape[0] for img in image_list]
        widths = [img.shape[1] for img in image_list]

        tensor_list = [self.transform(img).unsqueeze(0) for img in image_list]
        batch_tensor = torch.cat(tensor_list, dim=0).to(self.device)

        with torch.no_grad():
            self.timer.start("default")
            scores, boxes = self.net.forward(batch_tensor)
            print("Batch inference time: ", self.timer.end("default"))

        results = []
        for i in range(len(image_list)):
            result = self._postprocess(scores[i].to(cpu_device),
                                       boxes[i].to(cpu_device),
                                       widths[i],
                                       heights[i],
                                       top_k,
                                       prob_threshold or self.filter_threshold)
            results.append(result)

        return results  # List of (boxes, labels, probs)

    def _postprocess(self, scores, boxes, width, height, top_k, prob_threshold):
        picked_box_probs = []
        picked_labels = []

        for class_index in range(1, scores.size(1)):
            probs = scores[:, class_index]
            mask = probs > prob_threshold
            probs = probs[mask]
            if probs.size(0) == 0:
                continue
            subset_boxes = boxes[mask, :]
            box_probs = torch.cat([subset_boxes, probs.unsqueeze(1)], dim=1)
            box_probs = box_utils.nms(box_probs, self.nms_method,
                                      score_threshold=prob_threshold,
                                      iou_threshold=self.iou_threshold,
                                      sigma=self.sigma,
                                      top_k=top_k,
                                      candidate_size=self.candidate_size)
            picked_box_probs.append(box_probs)
            picked_labels.extend([class_index] * box_probs.size(0))

        if not picked_box_probs:
            return torch.tensor([]), torch.tensor([]), torch.tensor([])

        picked_box_probs = torch.cat(picked_box_probs, dim=0)
        picked_box_probs[:, 0] *= width
        picked_box_probs[:, 1] *= height
        picked_box_probs[:, 2] *= width
        picked_box_probs[:, 3] *= height

        return picked_box_probs[:, :4], torch.tensor(picked_labels), picked_box_probs[:, 4]
