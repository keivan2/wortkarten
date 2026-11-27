"""Watches the camera and hands back a photo each time a new card is held still."""
import io
import logging
import time

import numpy as np
from picamera2 import Picamera2
from PIL import ImageDraw

import config

log = logging.getLogger(__name__)

LORES = (160, 120)
MAX_EXPOSURE_US = 20000  # longer than this blurs a moving hand; use gain instead
MAX_GAIN = 8.0
EXPOSURE_CHECK_S = 2.0   # how often to re-check brightness while nobody shows a card
EMPTY_COVER = 0.08       # below this fraction of changed pixels the zone counts as empty
CROP_MARGIN = 0.08       # extra border around the zone in the photo sent to Gemini


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
        """Grey preview of the detection zone only."""
        frame = self.cam.capture_array("lores")[: LORES[1], : LORES[0]]  # Y plane
        x0, y0, x1, y1 = config.ZONE
        w, h = LORES
        return frame[int(y0 * h):int(y1 * h), int(x0 * w):int(x1 * w)].astype(np.int16)

    @staticmethod
    def _diff(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.mean(np.abs(a - b)))

    def _cover(self, cur: np.ndarray) -> float:
        """Fraction of the zone that differs clearly from the empty background."""
        return float(np.mean(np.abs(cur - self.background) > config.PIXEL_DIFF))

    def _jpeg(self, crop: bool = True, outline: bool = False,
              max_size: tuple[int, int] | None = None, quality: int = 90) -> bytes:
        """Photo of the zone (plus a margin, in case the card sticks out a little)."""
        img = self.cam.capture_image("main").convert("RGB")
        W, H = img.size
        x0, y0, x1, y1 = config.ZONE
        if outline:
            ImageDraw.Draw(img).rectangle(
                (x0 * W, y0 * H, x1 * W, y1 * H), outline=(255, 0, 0), width=4)
        if crop:
            m = CROP_MARGIN
            img = img.crop((int(max(x0 - m, 0) * W), int(max(y0 - m, 0) * H),
                            int(min(x1 + m, 1) * W), int(min(y1 + m, 1) * H)))
        if max_size:
            img.thumbnail(max_size)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()

    def _expose_for_card(self) -> None:
        """Re-expose for the card itself just before the photo. A white card held close is
        much brighter than the room, so with the room's exposure it burns out to pure white
        and the printed name disappears. Aim for the brightest parts (the paper) to sit just
        below white."""
        for _ in range(4):
            frame = self.cam.capture_array("lores")[: LORES[1], : LORES[0]]
            bright = float(np.percentile(frame, 98))
            if bright > 245:      # burnt out: we don't know how bright, so step down firmly
                factor = 0.55
            elif bright < 190:    # dim: brighten toward ~230
                factor = min(230 / max(bright, 1.0), 2.0)
            else:
                break
            new = min(max(self.light * factor, 100.0), MAX_EXPOSURE_US * MAX_GAIN)
            if abs(new - self.light) < 1:
                break             # at a limit
            self.light = new
            self._apply_light()
            log.debug("Card exposure: brightest parts %.0f -> light %.0f", bright, self.light)

    def photo(self, crop: bool = True) -> bytes:
        """Photo exposed for the card. crop=False sends the whole picture (button mode)."""
        room_light = self.light
        self._expose_for_card()
        jpeg = self._jpeg(crop=crop)
        if self.light != room_light:  # back to the room's exposure for motion detection
            self.light = room_light
            self._apply_light()
        return jpeg

    def adjust_exposure(self) -> None:
        """Call every few seconds while idle in button mode to follow the light."""
        self._correct_exposure(tolerance=35)

    def snapshot(self) -> bytes:
        """Full picture with the detection zone drawn in red, for aiming the camera."""
        return self._jpeg(crop=False, outline=True)

    def live_frame(self) -> bytes:
        """Small frame with the zone in red, for the live view in the browser."""
        return self._jpeg(crop=False, outline=True, max_size=(640, 480), quality=70)

    def wait_for_card(self) -> bytes:
        """Block until something big (close to the camera) is held still in the zone."""
        still = 0
        prev = self._grey()
        next_check = time.time() + EXPOSURE_CHECK_S
        next_note = 0.0
        while True:
            time.sleep(0.15)
            cur = self._grey()
            cover = self._cover(cur)
            change_vs_prev = self._diff(cur, prev)
            prev = cur
            if cover < EMPTY_COVER:
                # Empty zone: slowly follow lighting changes.
                self.background = (self.background * 0.9 + cur * 0.1).astype(np.int16)
                still = 0
                if time.time() >= next_check:
                    next_check = time.time() + EXPOSURE_CHECK_S
                    if self._correct_exposure(tolerance=35):
                        # The picture changed because we changed it, not because of a card.
                        self.background = prev = self._grey()
                continue
            if cover < config.MIN_COVER:
                still = 0  # something small or far away (a person walking by): ignore
                if time.time() >= next_note:  # helps tuning WK_MIN_COVER from the log
                    next_note = time.time() + 3
                    log.info("Ignored: something covers %.0f%% of the zone (needs %.0f%%)",
                             cover * 100, config.MIN_COVER * 100)
                continue
            still = still + 1 if change_vs_prev < config.STILL_THRESHOLD else 0
            if still >= config.STILL_FRAMES:
                log.info("Card detected (covers %.0f%% of the zone)", cover * 100)
                return self.photo()

    def wait_until_removed(self, timeout: float = 20.0) -> None:
        """Wait until the zone is empty again, so one card is only read once."""
        end = time.time() + timeout
        while time.time() < end:
            if self._cover(self._grey()) < EMPTY_COVER:
                return
            time.sleep(0.2)
        # Timed out (e.g. something was left in front of the camera): accept it as empty.
        self.background = self._grey()

    def close(self) -> None:
        self.cam.stop()
        self.cam.close()
