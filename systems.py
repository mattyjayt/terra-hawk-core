"""
System registry — loads systems.json and provides accessors.
"""
import json
import os
import subprocess
import threading
import time

_REGISTRY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "systems.json")
_lock = threading.Lock()
_systems: list[dict] = []
_status: dict[str, str] = {}  # system_id -> "online" | "offline"


def _load_registry() -> list[dict]:
    if not os.path.exists(_REGISTRY_PATH):
        return []
    with open(_REGISTRY_PATH) as f:
        data = json.load(f)
    systems = data.get("systems", [])
    ids = [s["id"] for s in systems]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate system IDs in {_REGISTRY_PATH}")
    return systems


def init():
    """Load the registry. Call once at startup."""
    global _systems
    _systems = _load_registry()
    for s in _systems:
        _status[s["id"]] = "unknown"
    threading.Thread(target=_health_loop, daemon=True).start()


def get_systems() -> list[dict]:
    """Return all systems with live status."""
    with _lock:
        result = []
        for s in _systems:
            entry = {**s, "status": _status.get(s["id"], "unknown")}
            result.append(entry)
        return result


def get_system(system_id: str) -> dict | None:
    with _lock:
        for s in _systems:
            if s["id"] == system_id:
                return {**s, "status": _status.get(s["id"], "unknown")}
    return None


def get_default_system_id() -> str | None:
    """Return the first system ID (for backwards-compatible endpoints)."""
    if _systems:
        return _systems[0]["id"]
    return None


def get_systems_with_camera() -> list[dict]:
    """Return systems that have a camera component with inference enabled."""
    return [
        s for s in _systems
        if s.get("components", {}).get("camera")
        and s["components"]["camera"].get("inference", {}).get("enabled", False)
    ]


def get_systems_with_sensors() -> list[dict]:
    """Return systems that have sensor components."""
    return [
        s for s in _systems
        if s.get("components", {}).get("sensors")
    ]


def _ping(ip: str) -> bool:
    if ip in ("localhost", "127.0.0.1"):
        return True
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            capture_output=True, timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False


def _health_loop():
    """Background loop: check each system controller IP every 30s."""
    while True:
        for s in _systems:
            ip = s.get("controller", {}).get("ip", "")
            online = _ping(ip)
            with _lock:
                _status[s["id"]] = "online" if online else "offline"
        time.sleep(30)
