from mqtt_client import MQTT_Client
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from data_models import sensor_state, cv_state
import asyncio
from video import start_thread

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mqtt = MQTT_Client()

clients = []

@app.get("/ping")
async def ping():
    return {
        "status": 200,
        "payload": "Hello, Jaime"
    }

@app.websocket("/ws/sensors")
async def sensors_ws(ws: WebSocket):
    await ws.accept()
    clients.append(ws)

    try:
        while True:
            await ws.send_json(sensor_state)
            await asyncio.sleep(0.2)
    except:
        clients.remove(ws)

@app.websocket("/ws/cv")
async def cv_websocket(ws: WebSocket):
    await ws.accept()
    clients.append(ws)

    try:
        while True:
            await ws.send_json(cv_state)
            await asyncio.sleep(0.033)  # ~30fps push rate
    except:
        clients.remove(ws)

@app.on_event("startup")
async def startup_event():
    start_thread()
