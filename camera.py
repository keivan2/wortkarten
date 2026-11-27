"""Watches the camera and hands back a photo each time a new card is held still."""
import io
import logging
import time

import numpy as np
from picamera2 import Picamera2

import config

log = logging.getLogger(__name__)

LORES = (160, 120)


class CardWatcher:
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
        time.sleep(2)  # let exposure settle
        self.background = self._grey()

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
