import os
import threading
import glob
from dotenv import load_dotenv

load_dotenv()

_lock = threading.Lock()

# RF-DETR models available via the rfdetr package (no local files needed)
RFDETR_REGISTRY = {
    "rfdetr-nano": {"name": "rfdetr-nano", "format": "rfdetr", "file": "rf-detr-nano.pth (auto-downloaded)", "size_mb": 349.0},
    "rfdetr-small": {"name": "rfdetr-small", "format": "rfdetr", "file": "rf-detr-small.pth (auto-downloaded)", "size_mb": 349.0},
}

_defaults = {
    "model": os.getenv("MODEL", "yolo26n"),
    "imgsz": int(os.getenv("IMGSZ", 640)),
    "confidence": float(os.getenv("CONFIDENCE", 0.5)),
    "iou": float(os.getenv("IOU", 0.7)),
}

_config = {**_defaults}

_model_swap_requested = False
_model_swap_target = None


def get_config() -> dict:
    with _lock:
        return {**_config}


def get_defaults() -> dict:
    return {**_defaults}


def update_config(patch: dict) -> dict:
    global _model_swap_requested, _model_swap_target
    with _lock:
        for key in ("confidence", "iou", "imgsz", "model"):
            if key in patch:
                if key == "confidence":
                    v = float(patch[key])
                    if not 0.0 <= v <= 1.0:
                        raise ValueError(f"confidence must be 0.0-1.0, got {v}")
                    _config["confidence"] = v
                elif key == "iou":
                    v = float(patch[key])
                    if not 0.0 <= v <= 1.0:
                        raise ValueError(f"iou must be 0.0-1.0, got {v}")
                    _config["iou"] = v
                elif key == "imgsz":
                    v = int(patch[key])
                    if v not in (320, 480, 640, 1024):
                        raise ValueError(f"imgsz must be 320/480/640/1024, got {v}")
                    _config["imgsz"] = v
                elif key == "model":
                    name = str(patch[key])
                    if not _model_exists(name):
                        raise FileNotFoundError(f"Model not found: {name}")
                    _config["model"] = name
                    _model_swap_requested = True
                    _model_swap_target = name
        return {**_config}


def consume_model_swap():
    global _model_swap_requested, _model_swap_target
    with _lock:
        if _model_swap_requested:
            _model_swap_requested = False
            return _model_swap_target
    return None


def list_models() -> list[dict]:
    base = os.path.dirname(os.path.abspath(__file__))
    models = []

    # Local .pt files (YOLO)
    for pt in glob.glob(os.path.join(base, "*.pt")):
        name = os.path.basename(pt).removesuffix(".pt")
        size_mb = os.path.getsize(pt) / (1024 * 1024)
        models.append({"name": name, "format": "pytorch", "file": os.path.basename(pt), "size_mb": round(size_mb, 1)})

    # Local NCNN model directories
    for d in glob.glob(os.path.join(base, "*_ncnn_model")):
        if os.path.isdir(d):
            name = os.path.basename(d)
            total = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d) if os.path.isfile(os.path.join(d, f)))
            size_mb = total / (1024 * 1024)
            models.append({"name": name, "format": "ncnn", "file": os.path.basename(d), "size_mb": round(size_mb, 1)})

    # RF-DETR models (always available via package)
    for entry in RFDETR_REGISTRY.values():
        models.append({**entry})

    return models


def _model_exists(name: str) -> bool:
    # RF-DETR models are always available
    if name.lower() in RFDETR_REGISTRY:
        return True
    base = os.path.dirname(os.path.abspath(__file__))
    return (
        os.path.isfile(os.path.join(base, f"{name}.pt"))
        or os.path.isdir(os.path.join(base, name))
        or os.path.isfile(os.path.join(base, name))
    )
