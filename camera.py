"""Watches the camera and hands back a photo each time a new card is held still."""
import io
import logging
import time

import numpy as np
from picamera2 import Picamera2

import config

log = logging.getLogger(__name__)

LORES = (160, 120)
MAX_EXPOSURE_US = 20000  # longer than this blurs a moving hand; use gain instead
MAX_GAIN = 8.0
EXPOSURE_CHECK_S = 2.0   # how often to re-check brightness while nobody shows a card


class CardWatcher:
    """Our own simple auto-exposure: this OV5647's built-in one locks at
    ~37 ms / 4x gain and overexposes the picture badly in daylight."""

    def __init__(self) -> None:
        tuning = None
        if config.CAMERA_TUNING:
            tuning = Picamera2.load_tuning_file(config.CAMERA_TUNING)
        self.cam = Picamera2(tuning=tuning)
        cfg = self.cam.create_still_configuration(
            main={"size": (1024, 768)},
            lores={"size": LORES, "format": "YUV420"},
            buffer_count=2,
        )
        self.cam.configure(cfg)
        self.cam.start()
        self.light = 10000.0  # exposure time (us) x analogue gain
        self._apply_light()
        for _ in range(8):  # converge from the starting guess
            if not self._correct_exposure(tolerance=15):
                break
        self.background = self._grey()

    def _apply_light(self) -> None:
        exposure = min(self.light, MAX_EXPOSURE_US)
        gain = min(max(self.light / exposure, 1.0), MAX_GAIN)
        self.light = exposure * gain
        self.cam.set_controls(
            {"AeEnable": False, "ExposureTime": int(exposure), "AnalogueGain": gain}
        )
        # New settings take a few frames to reach the sensor.
        for _ in range(10):
            meta = self.cam.capture_metadata()
            if abs(meta["ExposureTime"] - exposure) < exposure * 0.1:
                break
        self.cam.capture_metadata()  # one more frame fully exposed with the new values

    def _correct_exposure(self, tolerance: float) -> bool:
        """Nudge exposure toward the target brightness. Returns True if it changed."""
        mean = float(self._grey().mean())
        target = config.TARGET_BRIGHTNESS
        if abs(mean - target) <= tolerance:
            return False
        factor = min(max(target / max(mean, 1.0), 0.25), 4.0)
        old = self.light
        self.light = min(max(self.light * factor, 100.0), MAX_EXPOSURE_US * MAX_GAIN)
        if abs(self.light - old) < 1:
            return False  # already at a limit
        self._apply_light()
        log.debug("Exposure: brightness %.0f -> %.0f us x gain", mean, self.light)
        return True

    def _grey(self) -> np.ndarray:
        frame = self.cam.capture_array("lores")
        return frame[: LORES[1], : LORES[0]].astype(np.int16)  # Y plane only

    @staticmethod
    def _diff(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.mean(np.abs(a - b)))

    def _jpeg(self) -> bytes:
        buf = io.BytesIO()
        self.cam.capture_file(buf, format="jpeg")
        return buf.getvalue()

    def wait_for_card(self) -> bytes:
        """Block until something new is held still in front of the camera."""
        still = 0
        prev = self._grey()
        next_check = time.time() + EXPOSURE_CHECK_S
        while True:
            time.sleep(0.15)
            cur = self._grey()
            change_vs_bg = self._diff(cur, self.background)
            change_vs_prev = self._diff(cur, prev)
            prev = cur
            if change_vs_bg < config.MOTION_THRESHOLD:
                # Empty scene: slowly follow lighting changes.
                self.background = (self.background * 0.9 + cur * 0.1).astype(np.int16)
                still = 0
                if time.time() >= next_check:
                    next_check = time.time() + EXPOSURE_CHECK_S
                    if self._correct_exposure(tolerance=35):
                        # The picture changed because we changed it, not because of a card.
                        self.background = prev = self._grey()
                continue
            still = still + 1 if change_vs_prev < config.STILL_THRESHOLD else 0
            if still >= config.STILL_FRAMES:
                log.info("Card detected (change %.1f)", change_vs_bg)
                return self._jpeg()

    def wait_until_removed(self, timeout: float = 20.0) -> None:
        """Wait until the scene is back to empty, so one card is only read once."""
        end = time.time() + timeout
        while time.time() < end:
            if self._diff(self._grey(), self.background) < config.MOTION_THRESHOLD:
                return
            time.sleep(0.2)
        # Timed out (e.g. lighting changed for good): accept the new scene as empty.
        self.background = self._grey()

    def close(self) -> None:
        self.cam.stop()
        self.cam.close()
