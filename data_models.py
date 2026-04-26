"""
Shared state models — keyed by system ID for multi-system support.
Legacy flat dicts (sensor_state, cv_state, inference_stats) are aliases
to the default system for backwards compatibility.
"""
import threading

_lock = threading.Lock()

# Per-system state: { system_id: { ... } }
_sensor_states: dict[str, dict] = {}
_cv_states: dict[str, dict] = {}
_inference_stats_all: dict[str, dict] = {}

_default_system_id: str | None = None


def init_system(system_id: str, is_default: bool = False):
    """Initialise state dicts for a system."""
    global _default_system_id
    with _lock:
        if system_id not in _sensor_states:
            _sensor_states[system_id] = {
                "status": "idle",
                "temperature": None,
                "humidity": None,
                "soil": None,
            }
        if system_id not in _cv_states:
            _cv_states[system_id] = {
                "timestamp": None,
                "resolution": None,
                "objects": [],
            }
        if system_id not in _inference_stats_all:
            _inference_stats_all[system_id] = {
                "fps": 0,
                "latency_ms": 0,
                "active_tracks": 0,
            }
        if is_default or _default_system_id is None:
            _default_system_id = system_id


def get_sensor_state(system_id: str | None = None) -> dict:
    sid = system_id or _default_system_id
    if sid and sid in _sensor_states:
        return _sensor_states[sid]
    return {"status": "idle", "temperature": None, "humidity": None, "soil": None}


def get_cv_state(system_id: str | None = None) -> dict:
    sid = system_id or _default_system_id
    if sid and sid in _cv_states:
        return _cv_states[sid]
    return {"timestamp": None, "resolution": None, "objects": []}


def get_inference_stats(system_id: str | None = None) -> dict:
    sid = system_id or _default_system_id
    if sid and sid in _inference_stats_all:
        return _inference_stats_all[sid]
    return {"fps": 0, "latency_ms": 0, "active_tracks": 0}


def update_sensor_state(system_id: str, data: dict):
    if system_id in _sensor_states:
        _sensor_states[system_id].update(data)


def update_cv_state(system_id: str, data: dict):
    if system_id in _cv_states:
        _cv_states[system_id].update(data)


def update_inference_stats(system_id: str, data: dict):
    if system_id in _inference_stats_all:
        _inference_stats_all[system_id].update(data)


# ── Legacy aliases (backwards compatibility) ────────────────────────────────
# These reference the default system's state directly.
# Modules that import sensor_state/cv_state/inference_stats still work.

class _ProxyDict(dict):
    """Dict that proxies reads/writes to the default system's state."""
    def __init__(self, getter):
        super().__init__()
        self._getter = getter

    def __getitem__(self, key):
        return self._getter()[key]

    def __setitem__(self, key, value):
        self._getter()[key] = value

    def __contains__(self, key):
        return key in self._getter()

    def __iter__(self):
        return iter(self._getter())

    def __len__(self):
        return len(self._getter())

    def get(self, key, default=None):
        return self._getter().get(key, default)

    def update(self, data):
        self._getter().update(data)

    def items(self):
        return self._getter().items()

    def keys(self):
        return self._getter().keys()

    def values(self):
        return self._getter().values()


sensor_state = _ProxyDict(lambda: get_sensor_state())
cv_state = _ProxyDict(lambda: get_cv_state())
inference_stats = _ProxyDict(lambda: get_inference_stats())
