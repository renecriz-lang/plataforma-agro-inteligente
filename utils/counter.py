import json
import os
import threading

_LOCK = threading.Lock()
_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "counter.json")


def _read() -> dict:
    if os.path.exists(_FILE):
        try:
            with open(_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"total": 0}


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_FILE), exist_ok=True)
    with open(_FILE, "w") as f:
        json.dump(data, f)


def increment() -> int:
    """Incrementa o contador e retorna o novo total."""
    with _LOCK:
        data = _read()
        data["total"] += 1
        _write(data)
        return data["total"]


def get_count() -> int:
    return _read().get("total", 0)


def reset() -> None:
    with _LOCK:
        _write({"total": 0})
