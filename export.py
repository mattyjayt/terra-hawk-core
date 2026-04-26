import os
from dotenv import load_dotenv
from ultralytics import YOLO

load_dotenv()

model = YOLO(f"{os.getenv("MODEL")}")

model.export(format="ncnn", half=True)