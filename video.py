import os
from dotenv import load_dotenv
import cv2
import threading
import time
from data_models import update_cv_state, update_inference_stats
from config import get_config, consume_model_swap
from systems import get_systems_with_camera
from ultralytics import YOLO
from rfdetr import RFDETRNano, RFDETRSmall
import supervision as sv

load_dotenv()

RECONNECT_DELAY = float(os.getenv("RECONNECT_DELAY", 3))
MAX_CONSECUTIVE_FAILURES = int(os.getenv("MAX_CONSECUTIVE_FAILURES", 10))

# ── Model registry ──────────────────────────────────────────────────────────

RFDETR_MODELS = {
    "rfdetr-nano": RFDETRNano,
    "rfdetr-small": RFDETRSmall,
}


def is_rfdetr(name: str) -> bool:
    return name.lower() in RFDETR_MODELS


def load_model(name: str):
    """Load a YOLO or RF-DETR model by name."""
    if is_rfdetr(name):
        cls = RFDETR_MODELS[name.lower()]
        return cls(device="cpu")
    return YOLO(name, task="detect")


def get_class_names(model) -> list[str]:
    if hasattr(model, "class_names"):
        return model.class_names
    if hasattr(model, "names"):
        return list(model.names.values())
    return []


def run_inference(model, frame, cfg: dict) -> sv.Detections:
    if hasattr(model, "class_names"):
        return model.predict(frame, threshold=cfg["confidence"])
    else:
        result = model(
            source=frame,
            imgsz=cfg["imgsz"],
            conf=cfg["confidence"],
            iou=cfg["iou"],
            verbose=False,
        )[0]
        return sv.Detections.from_ultralytics(result)


# ── Per-system pipeline ─────────────────────────────────────────────────────

_model_lock = threading.Lock()
_shared_model = None
_shared_tracker_per_system: dict[str, sv.ByteTrack] = {}


def _get_shared_model(cfg: dict):
    """Get or load the shared model (all systems share one model instance)."""
    global _shared_model
    if _shared_model is None:
        _shared_model = load_model(cfg["model"])
    return _shared_model


def open_capture(stream_url: str) -> cv2.VideoCapture:
    while True:
        print(f"Connecting to stream: {stream_url}")
        cap = cv2.VideoCapture(stream_url)
        if cap.isOpened():
            print(f"Successfully connected to {stream_url}")
            return cap
        cap.release()
        print(f"Failed to open {stream_url}, retrying in {RECONNECT_DELAY}s...")
        time.sleep(RECONNECT_DELAY)


def reader_thread(system_id: str, stream_url: str, frame_store: dict):
    """Reads frames from a system's stream, keeps only the latest."""
    cap = open_capture(stream_url)
    consecutive_failures = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            consecutive_failures += 1
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                print(f"[{system_id}] Too many failures, reconnecting...")
                cap.release()
                time.sleep(RECONNECT_DELAY)
                cap = open_capture(stream_url)
                consecutive_failures = 0
            time.sleep(0.01)
            continue

        consecutive_failures = 0
        with frame_store["lock"]:
            frame_store["frame"] = frame


def inference_thread(system_id: str, frame_store: dict):
    """Grabs the latest frame for a system, runs inference, updates state."""
    global _shared_model

    while True:
        # Check for model hot-swap (applies to all systems)
        swap_target = consume_model_swap()
        if swap_target is not None:
            print(f"[{system_id}] Hot-swapping model to: {swap_target}")
            try:
                new_model = load_model(swap_target)
                with _model_lock:
                    _shared_model = new_model
                    # Reset all trackers
                    for sid in _shared_tracker_per_system:
                        _shared_tracker_per_system[sid] = sv.ByteTrack()
                print(f"[{system_id}] Model swapped successfully to: {swap_target}")
            except Exception as e:
                print(f"[{system_id}] Model swap failed: {e}")

        with frame_store["lock"]:
            frame = frame_store["frame"]

        if frame is None:
            time.sleep(0.01)
            continue

        cfg = get_config()
        h, w, _ = frame.shape

        t0 = time.time()
        with _model_lock:
            model = _get_shared_model(cfg)
            detections = run_inference(model, frame, cfg)
            class_names = get_class_names(model)
        t1 = time.time()

        tracker = _shared_tracker_per_system.get(system_id)
        if tracker is None:
            tracker = sv.ByteTrack()
            _shared_tracker_per_system[system_id] = tracker

        detections = tracker.update_with_detections(detections)

        latency_ms = (t1 - t0) * 1000
        fps = 1.0 / (t1 - t0) if (t1 - t0) > 0 else 0

        objects = []
        for box, class_id, confidence, tracker_id in zip(
            detections.xyxy,
            detections.class_id,
            detections.confidence,
            detections.tracker_id,
        ):
            x1, y1, x2, y2 = box
            label = class_names[int(class_id)] if int(class_id) < len(class_names) else f"class_{class_id}"
            objects.append({
                "id": int(tracker_id) if tracker_id is not None else None,
                "label": label,
                "confidence": round(float(confidence), 3),
                "bbox": {
                    "x": float(x1 / w),
                    "y": float(y1 / h),
                    "width": float((x2 - x1) / w),
                    "height": float((y2 - y1) / h),
                },
            })

        update_cv_state(system_id, {
            "timestamp": time.time(),
            "resolution": f"{w}x{h}",
            "objects": objects,
        })

        update_inference_stats(system_id, {
            "fps": round(fps, 1),
            "latency_ms": round(latency_ms, 1),
            "active_tracks": len(objects),
        })


def start_pipelines():
    """Spawn reader + inference threads for every system with a camera."""
    systems = get_systems_with_camera()

    if not systems:
        print("[CV] No systems with cameras found in registry.")
        return

    for s in systems:
        system_id = s["id"]
        camera = s["components"]["camera"]
        stream_url = camera["stream_url"]
        runs_on = camera.get("inference", {}).get("runs_on", "central")

        if runs_on not in ("self", "central"):
            print(f"[{system_id}] Unknown runs_on: {runs_on}, skipping.")
            continue

        # For "self" systems running on this machine, or "central" systems
        # where we pull the stream — both use the same pipeline
        frame_store = {"frame": None, "lock": threading.Lock()}

        print(f"[CV] Starting pipeline for {system_id} ({s['name']}) — {stream_url}")
        threading.Thread(target=reader_thread, args=(system_id, stream_url, frame_store), daemon=True).start()
        threading.Thread(target=inference_thread, args=(system_id, frame_store), daemon=True).start()


# ── Legacy alias ────────────────────────────────────────────────────────────
start_thread = start_pipelines
