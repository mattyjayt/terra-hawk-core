import systems
from data_models import (
    init_system, get_sensor_state, get_cv_state, get_inference_stats,
    sensor_state, cv_state, inference_stats,
)
from mqtt_client import MQTT_Client
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from config import get_config, get_defaults, update_config, list_models
import asyncio
from video import start_pipelines

# ── Initialise system registry ──────────────────────────────────────────────
systems.init()
for i, s in enumerate(systems.get_systems()):
    init_system(s["id"], is_default=(i == 0))

# ── App ─────────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mqtt = MQTT_Client()


# ── Health ──────────────────────────────────────────────────────────────────

@app.get("/ping")
async def ping():
    return {"status": 200, "payload": "Hello, Jaime"}


# ── Systems ─────────────────────────────────────────────────────────────────

@app.get("/systems")
async def list_systems():
    return {"systems": systems.get_systems()}


@app.get("/systems/{system_id}")
async def get_system(system_id: str):
    s = systems.get_system(system_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"System not found: {system_id}")
    return s


# ── Settings ────────────────────────────────────────────────────────────────

@app.get("/settings")
async def get_settings():
    cfg = get_config()
    return {
        "config": cfg,
        "defaults": get_defaults(),
        "stats": dict(inference_stats),
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


# ── WebSockets (per-system) ─────────────────────────────────────────────────

@app.websocket("/ws/sensors/{system_id}")
async def sensors_ws_system(ws: WebSocket, system_id: str):
    await ws.accept()
    try:
        while True:
            await ws.send_json(get_sensor_state(system_id))
            await asyncio.sleep(0.2)
    except:
        pass


@app.websocket("/ws/cv/{system_id}")
async def cv_ws_system(ws: WebSocket, system_id: str):
    await ws.accept()
    try:
        while True:
            await ws.send_json(get_cv_state(system_id))
            await asyncio.sleep(0.02)
    except:
        pass


# ── WebSockets (legacy — default system) ────────────────────────────────────

@app.websocket("/ws/sensors")
async def sensors_ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(get_sensor_state())
            await asyncio.sleep(0.2)
    except:
        pass


@app.websocket("/ws/cv")
async def cv_websocket(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            await ws.send_json(get_cv_state())
            await asyncio.sleep(0.02)
    except:
        pass


# ── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    start_pipelines()
