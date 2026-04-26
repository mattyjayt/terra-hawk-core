import os
from dotenv import load_dotenv
import cv2
import threading
import time
from data_models import cv_state, inference_stats
from config import get_config, consume_model_swap
from ultralytics import YOLO
import supervision as sv

load_dotenv()

RTSP_URL = f"rtsp://{os.getenv('HOST', 'localhost')}:8554/stream"
RECONNECT_DELAY = float(os.getenv("RECONNECT_DELAY", 3))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", 10))

_model_lock = threading.Lock()
model = YOLO(get_config()["model"], task="detect")
tracker = sv.ByteTrack()

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
    global _latest_frame, model, tracker

    while True:
        # Check for model hot-swap
        swap_target = consume_model_swap()
        if swap_target is not None:
            print(f"[CV] Hot-swapping model to: {swap_target}")
            try:
                new_model = YOLO(swap_target, task="detect")
                with _model_lock:
                    model = new_model
                    tracker = sv.ByteTrack()
                print(f"[CV] Model swapped successfully to: {swap_target}")
            except Exception as e:
                print(f"[CV] Model swap failed: {e}")

        with _frame_lock:
            frame = _latest_frame

        if frame is None:
            time.sleep(0.01)
            continue

        cfg = get_config()
        h, w, _ = frame.shape

        t0 = time.time()
        with _model_lock:
            result = model(source=frame, imgsz=cfg["imgsz"], conf=cfg["confidence"], iou=cfg["iou"], verbose=False)[0]
            current_model = model
        t1 = time.time()

        detections = sv.Detections.from_ultralytics(result)
        detections = tracker.update_with_detections(detections)

        latency_ms = (t1 - t0) * 1000
        fps = 1.0 / (t1 - t0) if (t1 - t0) > 0 else 0

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
                "label": current_model.names[int(class_id)],
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

        inference_stats.update({
            "fps": round(fps, 1),
            "latency_ms": round(latency_ms, 1),
            "active_tracks": len(objects),
        })


def start_thread():
    threading.Thread(target=reader_thread, daemon=True).start()
    threading.Thread(target=inference_thread, daemon=True).start()
