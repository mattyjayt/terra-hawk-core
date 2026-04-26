import cv2
import threading
import time
from data_models import cv_state
from ultralytics import YOLO
import supervision as sv

RTSP_URL = "rtsp://localhost:8554/stream"
RECONNECT_DELAY = 3.0
MAX_CONSECUTIVE_FAILURES = 10

model = YOLO("./yolo26n_ncnn_model", task="detect")
tracker = sv.ByteTrack()

# Shared state between reader and inference threads
_latest_frame = None
_frame_lock = threading.Lock()


def open_capture() -> cv2.VideoCapture:
    while True:
        print("Connecting to RTSP stream...")
        cap = cv2.VideoCapture(RTSP_URL)
        if cap.isOpened():
            print("Successfully connected to RTSP stream.")
            return cap
        cap.release()
        print(f"Failed to open stream, retrying in {RECONNECT_DELAY}s...")
        time.sleep(RECONNECT_DELAY)


def reader_thread():
    """Reads frames as fast as possible, keeps only the latest."""
    global _latest_frame
    cap = open_capture()
    consecutive_failures = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print("Too many consecutive failures, reconnecting...")
                cap.release()
                time.sleep(RECONNECT_DELAY)
                cap = open_capture()
                consecutive_failures = 0
            time.sleep(0.01)
            continue

        consecutive_failures = 0
        with _frame_lock:
            _latest_frame = frame


def inference_thread():
    """Grabs the latest frame, runs YOLO, updates cv_state."""
    global _latest_frame

    while True:
        with _frame_lock:
            frame = _latest_frame

        if frame is None:
            time.sleep(0.01)
            continue

        h, w, _ = frame.shape

        result = model(source=frame, imgsz=640, conf= 0.5, iou=0.7, verbose=False)[0]
        detections = sv.Detections.from_ultralytics(result)
        detections = tracker.update_with_detections(detections)

        objects = []
        for box, class_id, confidence, tracker_id in zip(
            detections.xyxy,
            detections.class_id,
            detections.confidence,
            detections.tracker_id
        ):
            x1, y1, x2, y2 = box
            objects.append({
                "id": int(tracker_id) if tracker_id is not None else None,
                "label": model.names[int(class_id)],
                "confidence": round(float(confidence), 3),
                "bbox": {
                    "x": float(x1 / w),
                    "y": float(y1 / h),
                    "width": float((x2 - x1) / w),
                    "height": float((y2 - y1) / h)
                }
            })

        cv_state.update({
            "timestamp": time.time(),
            "resolution": f"{w}x{h}",
            "objects": objects
        })


def start_thread():
    threading.Thread(target=reader_thread, daemon=True).start()
    threading.Thread(target=inference_thread, daemon=True).start()
