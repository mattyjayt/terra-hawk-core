from ultralytics import YOLO

model = YOLO("yolo26n")

model.export(format="ncnn", half=True)