"""Settings, read from environment variables (see .env)."""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_env_file(BASE_DIR / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Tried in order; the next one is used if a model is busy or fails.
GEMINI_MODELS = os.environ.get(
    "GEMINI_MODELS", "gemini-3.5-flash-lite,gemini-3.5-flash"
).split(",")
GEMINI_TIMEOUT_MS = int(os.environ.get("GEMINI_TIMEOUT_MS", "15000"))

VOICE = os.environ.get("WK_VOICE", "de-DE-KatjaNeural")
VOICE_RATE = os.environ.get("WK_VOICE_RATE", "-15%")  # a bit slower for kids
AUDIO_DEVICE = os.environ.get("WK_AUDIO_DEVICE", "")  # e.g. "hw:0,0"; empty = default

# The IR-CUT/night-vision OV5647 shows pink colours with the normal tuning.
CAMERA_TUNING = os.environ.get("WK_CAMERA_TUNING", "ov5647_noir.json")

# Card detection (tuned on the low-res grey preview, values 0-255)
MOTION_THRESHOLD = float(os.environ.get("WK_MOTION_THRESHOLD", "12"))
STILL_THRESHOLD = float(os.environ.get("WK_STILL_THRESHOLD", "4"))
STILL_FRAMES = int(os.environ.get("WK_STILL_FRAMES", "4"))

CACHE_DIR = BASE_DIR / "cache"
LOG_FILE = BASE_DIR / "gelernte_woerter.jsonl"
