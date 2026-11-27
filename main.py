"""Wortkarten: hold a picture card in front of the camera, hear the German word.

    python main.py              # run with the camera
    python main.py --image x.jpg  # test recognition + speech with a photo
"""
import argparse
import json
import logging
import random
import time

import config
import speaker
from recognizer import Recognizer, Result

log = logging.getLogger("wortkarten")

PRAISE = ["Super!", "Toll!", "Prima!", "Sehr gut!"]
UNKNOWN = "Hmm, das erkenne ich nicht. Halt die Karte bitte still vor die Kamera."


def announce(result: Result | None) -> None:
    if result is None:
        speaker.say(UNKNOWN)
        return
    log.info("-> %s (%s)", result.phrase, result.english)
    speaker.say(f"Das ist {result.phrase}.")
    time.sleep(0.4)
    speaker.say(f"{result.phrase}!")  # repeat the word on its own
    with config.LOG_FILE.open("a") as f:
        f.write(json.dumps({
            "zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
            "wort": result.word, "artikel": result.article, "englisch": result.english,
        }, ensure_ascii=False) + "\n")


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
                speaker.say("Oh, ich habe gerade keine Verbindung zum Internet.")
                result = None
            else:
                announce(result)
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
