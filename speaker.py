"""German text-to-speech with a local cache, so repeated words play instantly."""
import asyncio
import hashlib
import logging
import subprocess

import edge_tts

import config

log = logging.getLogger(__name__)


def _cache_path(text: str):
    key = f"{config.VOICE}|{config.VOICE_RATE}|{text}"
    return config.CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest()[:16] + ".mp3")


async def _synthesize(text: str, path) -> None:
    tts = edge_tts.Communicate(text, config.VOICE, rate=config.VOICE_RATE)
    await tts.save(str(path))


def say(text: str) -> None:
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
            return
    cmd = ["mpg123", "-q"]
    if config.AUDIO_DEVICE:
        cmd += ["-a", config.AUDIO_DEVICE]
    subprocess.run(cmd + [str(path)], check=False)
