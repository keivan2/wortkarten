"""Ask Gemini what is shown on a picture card, answered in German."""
import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

import config

log = logging.getLogger(__name__)

PROMPT = """Ein kleines Kind hält eine Lernkarte vor eine Kamera.
Die Karten haben ein Bild und darunter den Namen als gedruckten Text
(z. B. ein Farbklecks mit "Rot" darunter, oder eine Kuh mit "Kuh" darunter).
Das Foto kann gedreht, schräg oder leicht unscharf sein.
Ignoriere die Hand, das Kind und den Hintergrund – nur die Karte zählt.

1. Lies zuerst den gedruckten Text auf der Karte. Der Text ist die richtige Antwort,
   auch wenn das Bild etwas anderes zu zeigen scheint.
   - Ist der Text deutsch, übernimm ihn genau (nur Groß-/Kleinschreibung korrigieren).
   - Ist er in einer anderen Sprache, übersetze ihn ins Deutsche.
   - Steht schon ein Artikel dabei ("die Kuh"), trenne ihn in "artikel" und "wort".
2. Nur wenn kein Text lesbar ist: bestimme das Motiv aus dem Bild.

Antworte NUR mit JSON in genau diesem Format:
{"gefunden": true, "text": "Kuh", "quelle": "text", "wort": "Kuh", "artikel": "die", "englisch": "cow"}
- "text": der Text genau so, wie er auf der Karte steht ("" wenn keiner lesbar ist).
- "quelle": "text" wenn die Antwort vom gedruckten Text kommt, sonst "bild".
- "wort": das deutsche Wort, großgeschrieben, Substantive im Singular.
- "artikel": der, die oder das; bei Farben, Zahlen und Buchstaben leer: "".
- Wenn keine Karte zu sehen ist: {"gefunden": false}
"""


@dataclass
class Result:
    word: str
    article: str
    english: str
    text: str = ""      # text as printed on the card
    source: str = ""    # "text" (read from the card) or "bild" (guessed from the picture)

    @property
    def phrase(self) -> str:
        return f"{self.article} {self.word}".strip()


class Recognizer:
    def __init__(self) -> None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY missing - put it in .env")
        self.client = genai.Client(
            api_key=config.GEMINI_API_KEY,
            http_options=types.HttpOptions(timeout=config.GEMINI_TIMEOUT_MS),
        )

    def _ask(self, jpeg: bytes):
        """Try each configured model in turn; raise the last error if all fail."""
        error: Exception | None = None
        for model in config.GEMINI_MODELS:
            try:
                return self.client.models.generate_content(
                    model=model.strip(),
                    contents=[types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), PROMPT],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json", temperature=0.1
                    ),
                )
            except Exception as e:  # busy (503), quota, timeout ...
                log.warning("Model %s failed: %s", model, str(e)[:200])
                error = e
        raise error or RuntimeError("no Gemini model configured")

    def identify(self, jpeg: bytes) -> Result | None:
        response = self._ask(jpeg)
        log.debug("Gemini raw answer: %s", response.text)
        try:
            data = json.loads(response.text)
        except (json.JSONDecodeError, TypeError):
            log.warning("Unparseable answer: %r", response.text)
            return None
        if isinstance(data, list) and data:  # Gemini sometimes wraps the object in a list
            data = data[0]
        if not isinstance(data, dict) or not data.get("gefunden") or not data.get("wort"):
            return None
        article = str(data.get("artikel", "")).lower().strip()
        if article not in ("der", "die", "das"):
            article = ""
        return Result(
            word=str(data["wort"]).strip(),
            article=article,
            english=str(data.get("englisch", "")).strip(),
            text=str(data.get("text", "")).strip(),
            source=str(data.get("quelle", "")).strip(),
        )
