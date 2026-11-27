"""Text to speech: ElevenLabs if a key is set, otherwise (or when it fails) Microsoft Edge's
free voices. Every sentence is cached as an MP3, so each one is only generated once."""
import asyncio
import hashlib
import logging
import time
from pathlib import Path

import edge_tts
import requests

import config

log = logging.getLogger(__name__)

ELEVENLABS_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}"
ELEVENLABS_PAUSE_S = 600  # after a failure (quota used up, offline ...) skip ElevenLabs this long
_elevenlabs_paused_until = 0.0


def _cache_path(engine_key: str, text: str) -> Path:
    digest = hashlib.sha1(f"{engine_key}|{text}".encode()).hexdigest()[:16]
    return config.CACHE_DIR / f"{digest}.mp3"


def _elevenlabs_key() -> str:
    return f"elevenlabs|{config.ELEVENLABS_VOICE}|{config.ELEVENLABS_MODEL}"


def _edge_key() -> str:
    return f"{config.VOICE}|{config.VOICE_RATE}"  # same format as before: old cache stays valid


def _elevenlabs(text: str, path: Path) -> None:
    r = requests.post(
        ELEVENLABS_URL.format(voice=config.ELEVENLABS_VOICE),
        headers={"xi-api-key": config.ELEVENLABS_API_KEY},
        params={"output_format": "mp3_44100_128"},
        json={"text": text, "model_id": config.ELEVENLABS_MODEL, "language_code": "de"},
        timeout=30,
    )
    if not r.ok or not r.headers.get("content-type", "").startswith("audio"):
        raise RuntimeError(f"ElevenLabs HTTP {r.status_code}: {r.text[:200]}")
    path.write_bytes(r.content)


def _edge(text: str, path: Path) -> None:
    async def run() -> None:
        await edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE).save(str(path))
    asyncio.run(run())


def _make(engine, text: str, path: Path) -> bool:
    tmp = path.with_suffix(".part")
    try:
        engine(text, tmp)
        tmp.rename(path)
        return True
    except Exception as e:
        log.warning("%s failed for %r: %s", engine.__name__.strip("_"), text, str(e)[:200])
        tmp.unlink(missing_ok=True)
        return False


def mp3_for(text: str) -> Path | None:
    """Path to an MP3 of the text, or None if no engine could produce one."""
    global _elevenlabs_paused_until
    config.CACHE_DIR.mkdir(exist_ok=True)
    if config.ELEVENLABS_API_KEY:
        path = _cache_path(_elevenlabs_key(), text)
        if path.exists():
            return path
        if time.monotonic() >= _elevenlabs_paused_until:
            if _make(_elevenlabs, text, path):
                return path
            _elevenlabs_paused_until = time.monotonic() + ELEVENLABS_PAUSE_S
            log.warning("Using the free voice for the next %d minutes", ELEVENLABS_PAUSE_S // 60)
    path = _cache_path(_edge_key(), text)
    if path.exists() or _make(_edge, text, path):
        return path
    return None
