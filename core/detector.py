#core/detector.py
# -*- coding: utf-8 -*-

"""
Vehicle detector module using OpenVINO
"""

import cv2
import numpy as np
import time
from pathlib import Path
from openvino.runtime import Core, get_version
from threading import Lock
from typing import Tuple, Optional, Dict, Any, Union, List

from config.settings import VEHICLE_CLASSES, COLORS, DEFAULT_CONF_THRESHOLD, DEFAULT_NMS_THRESHOLD

class VehicleDetector:
    """
    Vehicle detector class using OpenVINO IR models
    Supports both synchronous and asynchronous inference
    """
    def __init__(self,
                 model_path,
                 device="GPU",
                 conf_threshold=DEFAULT_CONF_THRESHOLD,
                 nms_threshold=DEFAULT_NMS_THRESHOLD,
                 async_mode=True,
                 num_requests=2):
        """
        Initialize detector with OpenVINO model

        Args:
            model_path (str): Path to OpenVINO IR model (.xml)
            device (str): Device to run inference on (CPU, GPU, AUTO)
            conf_threshold (float): Confidence threshold for detections
            nms_threshold (float): NMS threshold for detections
            async_mode (bool): Enable asynchronous inference
            num_requests (int): Number of async inference requests
        """
        self.model_path = Path(model_path)
        self.device = device
        self.conf_threshold = conf_threshold
        self.nms_threshold = nms_threshold
        self.async_mode = async_mode
        self.num_requests = num_requests if async_mode else 1
        self.current_request_id = 0
        self.next_request_id = 1
        self.is_async = async_mode
        self.infer_lock = Lock()

        # Performance metrics
        self.inference_times = []
        self.frame_count = 0
        self.fps = 0

        print(f"OpenVINO version: {get_version()}")
        print(f"Initializing detector with {model_path} on {device}")
        print(f"Async mode: {async_mode}, Requests: {num_requests}")

        self._initialize_model()

    def _initialize_model(self):
        """Initialize and compile OpenVINO model"""
        try:
            # Initialize OpenVINO runtime core
            self.core = Core()

            # Read model
            self.model = self.core.read_model(self.model_path)

            # Configure performance settings
            config = {"PERFORMANCE_HINT": "THROUGHPUT"}

            # Device-specific configurations
            if "CPU" in self.device:
                config["CPU_THROUGHPUT_STREAMS"] = "AUTO"

            if "GPU" in self.device:
                try:
                    supported = self.core.get_property("GPU", "SUPPORTED_CONFIG_KEYS")
                    if "GPU_THROUGHPUT_STREAMS" in supported:
                        config["GPU_THROUGHPUT_STREAMS"] = "AUTO"
                except Exception as e:
                    print(f"Warning: GPU configuration not applied - {str(e)}")

            # Compile model
            self.compiled_model = self.core.compile_model(
                self.model, device_name=self.device, config=config
            )

            # Create inference requests
            self.requests = [
                self.compiled_model.create_infer_request()
                for _ in range(self.num_requests)
            ]

            # Get input/output info
            input_tensor = self.compiled_model.input(0)
            self.input_name = input_tensor.any_name
            _, _, self.input_height, self.input_width = input_tensor.shape

            print(f"Model loaded successfully. Input shape: {self.input_width}x{self.input_height}")

        except Exception as e:
            print(f"Error initializing model: {str(e)}")
            raise

    def preprocess(self, frame):
        """
        Preprocess frame for network input

        Args:
            frame (numpy.ndarray): Input BGR frame

        Returns:
            numpy.ndarray: Preprocessed blob
        """
        # Resize to network input size
        blob = cv2.resize(frame, (self.input_width, self.input_height))

        # Normalize [0-255] to [0-1]
        blob = blob.astype(np.float32) / 255.0

        # HWC to NCHW format
        blob = blob.transpose(2, 0, 1)[None, ...]

        return blob

    def postprocess(self, frame, detections):
        """
        Process raw detections to get bounding boxes and class info

        Args:
            frame (numpy.ndarray): Original frame
            detections (numpy.ndarray): Network output

        Returns:
            tuple: (processed_frame, detection_results)
                processed_frame: Frame with drawings
                detection_results: Dict with detailed detection info
        """
        h, w = frame.shape[:2]

        # Reshape detections if needed
        if detections.ndim == 3:
            detections = detections.reshape(-1, detections.shape[2])

        # Process detections
        boxes = []
        scores = []
        class_ids = []

        for detection in detections:
            # Extract normalized coordinates
            x_center, y_center, box_width, box_height = detection[0:4]
            confidence = float(detection[4])

            # Skip low confidence detections
            if confidence < self.conf_threshold:
                continue

            # Get class with highest probability
            classes_probs = detection[5:]
            class_id = int(np.argmax(classes_probs))

            # Filter vehicle classes
            if class_id not in VEHICLE_CLASSES or classes_probs[class_id] < self.conf_threshold:
                continue

            # Convert to pixel coordinates
            x1 = int((x_center - box_width/2) * w)
            y1 = int((y_center - box_height/2) * h)
            x2 = int((x_center + box_width/2) * w)
            y2 = int((y_center + box_height/2) * h)

            # Add to detection lists
            boxes.append([x1, y1, x2, y2])
            scores.append(confidence)
            class_ids.append(class_id)

        # Apply NMS to remove overlapping boxes
        indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_threshold, self.nms_threshold)

        # Final results
        results = {
            "boxes": [],
            "scores": [],
            "classes": [],
            "class_names": [],
            "counts": {v: 0 for v in VEHICLE_CLASSES.values()},
            "total": 0
        }

        # Extract final detections after NMS
        if len(indices) > 0:
            for i in indices.flatten():
                class_id = class_ids[i]
                class_name = VEHICLE_CLASSES[class_id]

                results["boxes"].append(boxes[i])
                results["scores"].append(scores[i])
                results["classes"].append(class_id)
                results["class_names"].append(class_name)
                results["counts"][class_name] += 1
                results["total"] += 1

                # Draw boxes on the frame
                x1, y1, x2, y2 = boxes[i]
                color = COLORS.get(class_name, (0, 255, 0))

                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                cv2.putText(frame,
                            f"{class_name}: {scores[i]:.2f}",
                            (x1, y1 - 7),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            color,
                            2)

        return frame, results

    def infer_sync(self, frame):
        """
        Run synchronous inference

        Args:
            frame (numpy.ndarray): Input frame

        Returns:
            Tuple[numpy.ndarray, float]: Network output and inference time
        """
        with self.infer_lock:
            start_time = time.time()

            # Preprocess
            blob = self.preprocess(frame)

            # Run inference
            results = self.compiled_model({self.input_name: blob})[0]

            # Update performance metrics
            infer_time = (time.time() - start_time) * 1000
            self.inference_times.append(infer_time)
            self.frame_count += 1

            return results, infer_time

    def start_async_infer(self, frame):
        """
        Start asynchronous inference

        Args:
            frame (numpy.ndarray): Input frame
        """
        with self.infer_lock:
            # Check if request is busy - use proper error handling
            try:
                # Don't pass any arguments to wait()
                status = self.requests[self.next_request_id].wait()
                # Process status if needed
            except Exception as e:
                print(f"Warning: Issue checking request status - {str(e)}")

            # Preprocess
            blob = self.preprocess(frame)

            # Start async inference
            self.requests[self.next_request_id].start_async({self.input_name: blob})

    def wait_and_get_result(self):
        """
        Wait for current async request to complete and get result

        Returns:
            Tuple[numpy.ndarray, float]: Detections and inference time (ms)
        """
        with self.infer_lock:
            start_time = time.time()

            # Wait for current request
            self.requests[self.current_request_id].wait()

            # Get result
            detections = self.requests[self.current_request_id].get_output_tensor(0).data

            # Measure inference time
            infer_time = (time.time() - start_time) * 1000
            self.inference_times.append(infer_time)
            self.frame_count += 1

            # Update request ids
            self.current_request_id, self.next_request_id = self.next_request_id, self.current_request_id

            return detections, infer_time

    def detect(self, frame):
        """
        Run detection on frame (sync or async depending on configuration)

        For async mode, this needs to be called twice:
        First call: start_async_infer(frame_1)
        Second call: process previous frame with result

        Args:
            frame (numpy.ndarray): Input frame or None for async continuation

        Returns:
            Tuple[numpy.ndarray, float]: (detections, infer_time_ms)
                Will return (None, None) if async detection is not ready
        """
        if self.is_async:
            if frame is not None:
                # Start async inference for current frame
                self.start_async_infer(frame)
                # For the first frame, we don't have results yet
                if self.frame_count == 0:
                    return None, None

            # Get results from the previous inference
            return self.wait_and_get_result()
        else:
            # Synchronous mode is straightforward
            return self.infer_sync(frame)

    def get_performance_stats(self):
        """
        Get detector performance statistics

        Returns:
            dict: Performance metrics
        """
        if not self.inference_times:
            return {
                "avg_inference_time": 0,
                "fps": 0,
                "frames_processed": 0
            }

        avg_time = sum(self.inference_times) / len(self.inference_times)
        fps = 1000 / avg_time if avg_time > 0 else 0

        return {
            "avg_inference_time": avg_time,
            "fps": fps,
            "frames_processed": self.frame_count
        }

    def reset_stats(self):
        """Reset performance statistics"""
        self.inference_times = []
        self.frame_count = 0

    def draw_stats(self, frame):
        """
        Draw performance statistics on frame

        Args:
            frame (numpy.ndarray): Frame to draw on

        Returns:
            numpy.ndarray: Frame with statistics
        """
        stats = self.get_performance_stats()

        h = frame.shape[0]
        cv2.putText(frame, f"Infer: {stats['avg_inference_time']:.1f} ms",
                    (10, h - 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(frame, f"FPS: {stats['fps']:.1f}",
                    (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return frame