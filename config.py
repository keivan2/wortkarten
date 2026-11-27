"""Settings, read from environment variables (see .env)."""
import os
import re
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

# Optional: the child's name, used in the greeting "Hallo Anna! Zeig mir eine Karte ..."
CHILD_NAME = os.environ.get("WK_CHILD_NAME", "").strip()

# ElevenLabs (used when a key is set). Default: "Sarah" with the expressive v3 model.
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_VOICE = os.environ.get("WK_ELEVENLABS_VOICE", "EXAVITQu4vr4xnSDxMaL")
ELEVENLABS_MODEL = os.environ.get("WK_ELEVENLABS_MODEL", "eleven_v3")

# Free Microsoft Edge voice: used without an ElevenLabs key, or when ElevenLabs fails.
VOICE = os.environ.get("WK_VOICE", "de-DE-SeraphinaMultilingualNeural")
VOICE_RATE = os.environ.get("WK_VOICE_RATE", "-10%")  # a bit slower for kids
AUDIO_DEVICE = os.environ.get("WK_AUDIO_DEVICE", "")  # e.g. "hw:0,0"; empty = default
# Bluetooth speaker MAC address (paired + trusted with bluetoothctl). When it is off or out
# of range, sound falls back to AUDIO_DEVICE (the headphone jack).
BT_SPEAKER = os.environ.get("WK_BT_SPEAKER", "").strip().upper()
if BT_SPEAKER and not re.fullmatch(r"([0-9A-F]{2}:){5}[0-9A-F]{2}", BT_SPEAKER):
    raise ValueError(f"WK_BT_SPEAKER must look like 52:C5:EC:33:40:58, got {BT_SPEAKER!r}")

# The IR-CUT/night-vision OV5647 shows pink colours with the normal tuning.
CAMERA_TUNING = os.environ.get("WK_CAMERA_TUNING", "ov5647_noir.json")
# Our own auto-exposure aims for this average brightness (0-255) of the empty scene.
TARGET_BRIGHTNESS = float(os.environ.get("WK_TARGET_BRIGHTNESS", "110"))

# Card detection (tuned on the low-res grey preview, values 0-255)
# Only this box of the picture is watched: left, top, right, bottom as fractions 0-1.
ZONE = tuple(float(v) for v in os.environ.get("WK_ZONE", "0.1,0.05,0.9,0.95").split(","))
if len(ZONE) != 4 or not (0 <= ZONE[0] < ZONE[2] <= 1 and 0 <= ZONE[1] < ZONE[3] <= 1):
    raise ValueError(f"WK_ZONE must be 'left,top,right,bottom' between 0 and 1, got {ZONE}")
# A card must cover at least this fraction of the zone (= held close to the camera).
MIN_COVER = float(os.environ.get("WK_MIN_COVER", "0.35"))
PIXEL_DIFF = float(os.environ.get("WK_PIXEL_DIFF", "25"))  # how different a pixel must be
STILL_THRESHOLD = float(os.environ.get("WK_STILL_THRESHOLD", "4"))
STILL_FRAMES = int(os.environ.get("WK_STILL_FRAMES", "4"))

# "auto": read a card as soon as one is held still in the zone.
# "button": read the card only when the button is pressed (see button.py).
MODE = os.environ.get("WK_MODE", "auto").strip().lower()
if MODE not in ("auto", "button"):
    raise ValueError(f"WK_MODE must be 'auto' or 'button', got {MODE!r}")
MQTT_HOST = os.environ.get("WK_MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("WK_MQTT_PORT", "1883"))
# zigbee2mqtt publishes each device on zigbee2mqtt/<friendly name>; "+" matches any name.
BUTTON_TOPICS = [t.strip() for t in os.environ.get(
    "WK_BUTTON_TOPICS", "zigbee2mqtt/knopf").split(",") if t.strip()]

# Live camera view in the browser on this port (0 = off). No password: anyone on the home
# network can watch it.
LIVE_PORT = int(os.environ.get("WK_LIVE_PORT", "0"))
if not 0 <= LIVE_PORT <= 65535:
    raise ValueError(f"WK_LIVE_PORT must be a port number or 0, got {LIVE_PORT}")

# Every captured card photo is kept here for later review (set WK_SAVE_CAPTURES=0 to disable).
SAVE_CAPTURES = os.environ.get("WK_SAVE_CAPTURES", "1") != "0"
CAPTURES_DIR = BASE_DIR / "captures"

CACHE_DIR = BASE_DIR / "cache"
LOG_FILE = BASE_DIR / "gelernte_woerter.jsonl"
