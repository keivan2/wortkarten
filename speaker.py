"""German text-to-speech with a local cache, so repeated words play instantly."""
import asyncio
import hashlib
import logging
import subprocess
import threading

import edge_tts

import config

log = logging.getLogger(__name__)


def _cache_path(text: str):
    key = f"{config.VOICE}|{config.VOICE_RATE}|{text}"
    return config.CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".mp3")


async def _synthesize(text: str, path) -> None:
    tts = edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE)
    await tts.save(str(path))


# Set by stop() (e.g. from a button press in another thread): the current sentence is cut
# off and further say() calls are skipped until resume() is called.
_interrupted = threading.Event()
_lock = threading.Lock()
_player: subprocess.Popen | None = None


def stop() -> None:
    _interrupted.set()
    with _lock:
        if _player and _player.poll() is None:
            _player.terminate()


def resume() -> None:
    _interrupted.clear()


def say(text: str) -> bool:
    """Speak text. Returns False if it was interrupted by stop()."""
    global _player
    if _interrupted.is_set():
        return False
    config.CACHE_DIR.mkdir(exist_ok=True)
    path = _cache_path(text)
    if not path.exists():
        tmp = path.with_suffix(".part")
        try:
            asyncio.run(_synthesize(text, tmp))
            tmp.rename(path)
        except Exception:
            log.exception("Speech synthesis failed for %r", text)
            tmp.unlink(missing_ok=True)
            return True
    cmd = ["mpg123", "-q"]
    if config.AUDIO_DEVICE:
        cmd += ["-a", config.AUDIO_DEVICE]
    with _lock:
        if _interrupted.is_set():
            return False
        _player = subprocess.Popen(cmd + [str(path)])
    _player.wait()
    return not _interrupted.is_set()
