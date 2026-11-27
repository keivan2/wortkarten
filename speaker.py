"""Plays German speech: on the Bluetooth speaker if connected, else the wired output.
The MP3s come from tts.py (cached)."""
import logging
import subprocess
import threading
import time

import config
import tts

log = logging.getLogger(__name__)

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
    if _interrupted.is_set():
        return False
    path = tts.mp3_for(text)
    if path is None:
        log.error("No speech engine available for %r", text)
        return True
    device = _output_device()
    if not _play(path, device) and device != config.AUDIO_DEVICE and not _interrupted.is_set():
        log.warning("Bluetooth playback failed, using the wired output instead")
        _play(path, config.AUDIO_DEVICE)
    return not _interrupted.is_set()


def _play(path, device: str) -> bool:
    """Play one MP3 file. Returns True on success (or when cut off by stop())."""
    global _player
    cmd = ["mpg123", "-q"] + (["-a", device] if device else []) + [str(path)]
    with _lock:
        if _interrupted.is_set():
            return True
        # stderr is captured: the Bluetooth ALSA plugin prints lots of debug lines.
        _player = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, errors="replace")
    _, err = _player.communicate()
    if _player.returncode != 0 and not _interrupted.is_set():
        errors = [l for l in err.splitlines() if "] D: " not in l]
        log.warning("mpg123 on %r failed (%s): %s", device or "default",
                    _player.returncode, " | ".join(errors[-3:]))
        return False
    return True


# --- Bluetooth speaker -------------------------------------------------------------
RECONNECT_EVERY_S = 20
_watcher_started = False


def _bt_connected(mac: str) -> bool:
    try:
        out = subprocess.run(["bluetoothctl", "info", mac],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Connected: yes" in out


def _keep_connected(mac: str) -> None:
    """Background thread: whenever the speaker is switched on again, reconnect it.
    Speech never waits for this; until then it uses the wired output."""
    was_connected = None
    while True:
        connected = _bt_connected(mac)
        if not connected:
            try:
                subprocess.run(["bluetoothctl", "--timeout", "8", "connect", mac],
                               capture_output=True, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                pass
            connected = _bt_connected(mac)
        if connected != was_connected:
            log.info("Bluetooth speaker %s", "connected" if connected
                     else "not available, using the wired output")
            was_connected = connected
        time.sleep(RECONNECT_EVERY_S)


def start_bluetooth() -> None:
    """Start the reconnect thread (once). Called on startup and from say()."""
    global _watcher_started
    if config.BT_SPEAKER and not _watcher_started:
        _watcher_started = True
        threading.Thread(target=_keep_connected, args=(config.BT_SPEAKER,),
                         daemon=True, name="bt-speaker").start()


def _output_device() -> str:
    """The Bluetooth speaker if it is connected right now, else the wired output."""
    mac = config.BT_SPEAKER
    if not mac:
        return config.AUDIO_DEVICE
    start_bluetooth()
    if _bt_connected(mac):
        return f"bluealsa:DEV={mac},PROFILE=a2dp"
    return config.AUDIO_DEVICE
