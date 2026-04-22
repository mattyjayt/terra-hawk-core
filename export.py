from ultralytics import YOLO

model = YOLO("yolov8n")

model.export(format="onnx", int8=True, device="cpu")