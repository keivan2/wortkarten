"""Wortkarten: hold a picture card in front of the camera, hear the German word.

    python main.py              # run with the camera
    python main.py --image x.jpg  # test recognition + speech with a photo
"""
import argparse
import json
import logging
import random
import re
import time
from pathlib import Path

import config
import speaker
from recognizer import Recognizer, Result

log = logging.getLogger("wortkarten")

PRAISE = ["Super!", "Toll!", "Prima!", "Sehr gut!"]
UNKNOWN = "Hmm, das erkenne ich nicht. Halt die Karte bitte still vor die Kamera."


def save_capture(jpeg: bytes, label: str) -> Path | None:
    """Keep the photo for later review: captures/2026-11-27/093512_Kuh.jpg"""
    if not config.SAVE_CAPTURES:
        return None
    safe = re.sub(r"[^\wäöüÄÖÜß-]+", "_", label).strip("_") or "unbekannt"
    folder = config.CAPTURES_DIR / time.strftime("%Y-%m-%d")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{time.strftime('%H%M%S')}_{safe}.jpg"
        path.write_bytes(jpeg)
    except OSError:
        log.exception("Could not save capture")
        return None
    log.info("Saved %s", path.relative_to(config.BASE_DIR))
    return path


def announce(result: Result | None, image: Path | None = None) -> None:
    if result is None:
        speaker.say(UNKNOWN)
        return
    log.info("-> %s (%s) from %s, card text %r",
             result.phrase, result.english, result.source or "?", result.text)
    speaker.say(f"Das ist {result.phrase}.")
    time.sleep(0.4)
    speaker.say(f"{result.phrase}!")  # repeat the word on its own
    entry = {
        "zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wort": result.word, "artikel": result.article, "englisch": result.english,
        "kartentext": result.text, "quelle": result.source,
    }
    if image:
        entry["bild"] = str(image.relative_to(config.BASE_DIR))
    with config.LOG_FILE.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_image(path: str) -> None:
    with open(path, "rb") as f:
        announce(Recognizer().identify(f.read()))


def run_camera() -> None:
    from camera import CardWatcher  # imported here so --image works without a camera

    recognizer = Recognizer()
    watcher = CardWatcher()
    speaker.say("Hallo! Zeig mir eine Karte.")
    try:
        while True:
            jpeg = watcher.wait_for_card()
            speaker.say(random.choice(PRAISE))  # instant feedback while we ask Gemini
            try:
                result = recognizer.identify(jpeg)
            except Exception:
                log.exception("Recognition failed")
                save_capture(jpeg, "fehler")
                speaker.say("Oh, ich habe gerade keine Verbindung zum Internet.")
            else:
                image = save_capture(jpeg, result.word if result else "unbekannt")
                announce(result, image)
            watcher.wait_until_removed()
    finally:
        watcher.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="recognise this photo instead of using the camera")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.image:
        run_image(args.image)
    else:
        run_camera()


if __name__ == "__main__":
    main()
