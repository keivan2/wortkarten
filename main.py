"""Wortkarten: hold a picture card in front of the camera, hear the German word.

    python main.py              # run with the camera
    python main.py --image x.jpg  # test recognition + speech with a photo
    python main.py --snapshot s.jpg  # save the camera view with the detection zone in red
                                     # (stop the service first: it holds the camera)
"""
import argparse
import json
import logging
import re
import time
from pathlib import Path

import config
import speaker
from recognizer import NoCard, Recognizer, Result

log = logging.getLogger("wortkarten")

HELLO = f"Hallo {config.CHILD_NAME}!" if config.CHILD_NAME else "Hallo!"
UNKNOWN = "Hmm, das erkenne ich nicht. Halt die Karte bitte still vor die Kamera."
NO_CARD = "Ich sehe keine Karte. Halt sie vor die Kamera und drück nochmal."
OFFLINE = "Oh, ich habe gerade keine Verbindung zum Internet."


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


def log_word(result: Result, image: Path | None) -> None:
    entry = {
        "zeit": time.strftime("%Y-%m-%d %H:%M:%S"),
        "wort": result.word, "artikel": result.article, "englisch": result.english,
        "kartentext": result.text, "quelle": result.source,
    }
    if image:
        entry["bild"] = str(image.relative_to(config.BASE_DIR))
    with config.LOG_FILE.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def announce(result: Result | NoCard | None, image: Path | None = None,
             button: bool = False) -> None:
    """Speak the result. Each say() returns False when a button press cut it off."""
    if isinstance(result, NoCard):
        if button:  # she pressed on purpose, so tell her what to do
            speaker.say(NO_CARD)
        else:       # something else triggered the camera: stay quiet
            log.info("-> no card in the photo, staying quiet")
        return
    if result is None:
        speaker.say(UNKNOWN)
        return
    log.info("-> %s (%s) from %s, card text %r",
             result.phrase, result.english, result.source or "?", result.text)
    log_word(result, image)
    sentence = f"Das ist {result.phrase}."
    if config.CHILD_NAME:  # "Anna, das ist die Kuh."
        sentence = f"{config.CHILD_NAME}, das ist {result.phrase}."
    if not speaker.say(sentence):
        return
    time.sleep(0.4)
    speaker.say(f"{result.phrase}!")  # repeat the word on its own


def recognise(recognizer: Recognizer, jpeg: bytes) -> tuple[Result | NoCard | None, Path | None]:
    """Ask Gemini and keep the photo. Raises if Gemini can't be reached."""
    try:
        result = recognizer.identify(jpeg)
    except Exception:
        save_capture(jpeg, "fehler")
        raise
    if isinstance(result, Result):
        label = result.word
    else:
        label = "keinekarte" if isinstance(result, NoCard) else "unbekannt"
    return result, save_capture(jpeg, label)


def run_image(path: str) -> None:
    with open(path, "rb") as f:
        announce(Recognizer().identify(f.read()))


def run_auto(recognizer: Recognizer, watcher) -> None:
    """Read a card as soon as one is held still in the zone."""
    speaker.say(f"{HELLO} Zeig mir eine Karte.")
    while True:
        jpeg = watcher.wait_for_card()
        try:
            result, image = recognise(recognizer, jpeg)
        except Exception:
            log.exception("Recognition failed")
            speaker.say(OFFLINE)
        else:
            announce(result, image)
        watcher.wait_until_removed()


def run_button(recognizer: Recognizer, watcher) -> None:
    """Read the card only when the button is pressed. A new press cuts off whatever
    is being said and reads the card that is there now."""
    from button import ButtonListener

    buttons = ButtonListener(on_press=speaker.stop)
    try:
        speaker.say(f"{HELLO} Zeig mir eine Karte und drück den Knopf.")
        while True:
            if not buttons.wait(timeout=2.0):
                watcher.adjust_exposure()
                continue
            press = buttons.presses
            speaker.resume()
            jpeg = watcher.photo()
            try:
                result, image = recognise(recognizer, jpeg)
            except Exception:
                log.exception("Recognition failed")
                speaker.say(OFFLINE)
                continue
            if buttons.presses != press:
                continue  # pressed again while we waited for Gemini: read the newer card
            announce(result, image, button=True)
    finally:
        buttons.close()


def run_camera() -> None:
    from camera import CardWatcher  # imported here so --image works without a camera

    recognizer = Recognizer()
    watcher = CardWatcher()
    log.info("Mode: %s", config.MODE)
    try:
        if config.MODE == "button":
            run_button(recognizer, watcher)
        else:
            run_auto(recognizer, watcher)
    finally:
        watcher.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", help="recognise this photo instead of using the camera")
    parser.add_argument("--snapshot", metavar="FILE",
                        help="save the camera view with the detection zone drawn in red")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.snapshot:
        from camera import CardWatcher
        watcher = CardWatcher()
        Path(args.snapshot).write_bytes(watcher.snapshot())
        watcher.close()
        log.info("Saved %s", args.snapshot)
    elif args.image:
        run_image(args.image)
    else:
        run_camera()


if __name__ == "__main__":
    main()
