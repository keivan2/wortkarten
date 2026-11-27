"""Ask Gemini what is shown on a picture card, answered in German."""
import json
import logging
from dataclasses import dataclass

from google import genai
from google.genai import types

import config

log = logging.getLogger(__name__)

PROMPT = """Ein kleines Kind hält eine Bildkarte vor eine Kamera.
Was ist auf der Karte abgebildet (Tier, Gegenstand, Essen, Fahrzeug, Farbe ...)?
Ignoriere die Hand, das Kind und den Hintergrund – nur das Motiv auf der Karte zählt.
Antworte NUR mit JSON in genau diesem Format:
{"gefunden": true, "wort": "Kuh", "artikel": "die", "englisch": "cow"}
- "wort": das einfache, kindgerechte deutsche Substantiv im Singular, großgeschrieben.
- "artikel": der, die oder das (bei Farben leer lassen: "").
- Wenn keine Karte oder kein klares Motiv zu sehen ist: {"gefunden": false}
"""


@dataclass
class Result:
    word: str
    article: str
    english: str

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
        if not isinstance(data, dict) or not data.get("gefunden") or not data.get("wort"):
            return None
        article = str(data.get("artikel", "")).lower().strip()
        if article not in ("der", "die", "das"):
            article = ""
        return Result(
            word=str(data["wort"]).strip(),
            article=article,
            english=str(data.get("englisch", "")).strip(),
        )
