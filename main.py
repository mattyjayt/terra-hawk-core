from mqtt_client import MQTT_Client
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from data_models import sensor_state, cv_state, inference_stats
from config import get_config, get_defaults, update_config, list_models
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


@app.get("/settings")
async def get_settings():
    cfg = get_config()
    return {
        "config": cfg,
        "defaults": get_defaults(),
        "stats": inference_stats,
    }


@app.get("/settings/models")
async def get_models():
    return {"models": list_models()}


@app.put("/settings")
async def put_settings(patch: dict):
    try:
        updated = update_config(patch)
        return {"config": updated}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
            await asyncio.sleep(0.02)
    except:
        clients.remove(ws)


@app.on_event("startup")
async def startup_event():
    start_thread()
