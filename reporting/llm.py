"""Very small Gemini client (standard library only).

Callers catch only LLMError. The API key is sent in a header, never in the URL, and is never logged.
"""

import json
import socket
import time
import urllib.error
import urllib.request

from django.conf import settings

TIMEOUT_SECONDS = 30
RETRY_WAIT_SECONDS = 3
URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(Exception):
    """Anything that went wrong while asking the model."""


def is_configured() -> bool:
    return bool(settings.GEMINI_API_KEY)


def _call(prompt: str, as_json: bool, retry: bool = True) -> str:
    if not is_configured():
        raise LLMError("Gemini API key is not configured.")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if as_json:
        body["generationConfig"] = {"responseMimeType": "application/json"}
    request = urllib.request.Request(
        URL.format(model=settings.GEMINI_MODEL),
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "x-goog-api-key": settings.GEMINI_API_KEY},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if response.status != 200:
                raise LLMError(f"Gemini returned HTTP {response.status}.")
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # 503 means the free tier is busy for a moment: wait briefly and try once more.
        if exc.code == 503 and retry:
            time.sleep(RETRY_WAIT_SECONDS)
            return _call(prompt, as_json, retry=False)
        raise LLMError(f"Gemini returned HTTP {exc.code}.") from exc
    except (socket.timeout, TimeoutError) as exc:
        raise LLMError("Gemini request timed out.") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise LLMError("Could not reach Gemini.") from exc
    except ValueError as exc:  # malformed JSON or bad UTF-8 in the reply
        raise LLMError("Gemini reply was not valid JSON.") from exc

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Gemini returned an empty or blocked response.") from exc
    if not isinstance(text, str) or not text.strip():
        raise LLMError("Gemini returned an empty response.")
    return text.strip()


def generate_text(prompt: str) -> str:
    return _call(prompt, as_json=False)


def generate_json(prompt: str) -> dict:
    text = _call(prompt, as_json=True)
    try:
        return json.loads(text)
    except ValueError as exc:
        raise LLMError("Gemini reply was not valid JSON.") from exc
