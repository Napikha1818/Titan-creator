"""Translator module for Chess Video Translator.

Uses Google Cloud Translation API (primary) with chess term pre-processing,
falling back to deep-translator (free Google Translate) if API key unavailable.
"""

import json
import logging
import os
import re
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from src.config import CHESS_TERM_MAPPING
from src.errors import TranslationError
from src.models import Segment, TranslatedSegment

logger = logging.getLogger(__name__)

_GOOGLE_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2"


class ChessTranslator:
    """Terjemahan teks Indonesia ke Inggris dengan dukungan istilah catur.

    Uses Google Cloud Translation API when API key is available,
    with placeholder-based chess term protection. Falls back to
    deep-translator (free) when no API key.
    """

    CHESS_TERMS: dict[str, str] = dict(CHESS_TERM_MAPPING)

    def __init__(
        self,
        api_key: str | None = None,
        gemini_api_key: str | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("GOOGLE_TRANSLATE_API_KEY")
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        self._use_gcp = bool(self.api_key)
        self._use_gemini = bool(self.gemini_api_key)

        if not self._use_gcp:
            logger.warning("No GOOGLE_TRANSLATE_API_KEY, falling back to deep-translator")
        if not self._use_gemini:
            logger.warning("No GEMINI_API_KEY, punctuation will use simple rules")

        # Sort terms by length (longest first) so multi-word terms like
        # "skak mat" are matched before single-word terms like "skak".
        self._sorted_terms = sorted(
            self.CHESS_TERMS.keys(), key=len, reverse=True
        )
        # Build placeholder mappings
        self._placeholder_to_english: dict[str, str] = {}
        self._term_to_placeholder: dict[str, str] = {}
        for i, term in enumerate(self._sorted_terms):
            placeholder = f"CHESSTERM{i:03d}"
            self._term_to_placeholder[term] = placeholder
            self._placeholder_to_english[placeholder] = self.CHESS_TERMS[term]

    def translate_segments(
        self, segments: list[Segment]
    ) -> list[TranslatedSegment]:
        """Translate all segments. Falls back to original text if translation fails per segment."""
        translated: list[TranslatedSegment] = []

        for segment in segments:
            try:
                translated_text = self.translate_text(segment.text)
            except Exception:
                logger.warning(
                    "Translation failed for segment [%.2f-%.2f], using original text as fallback",
                    segment.start,
                    segment.end,
                )
                translated_text = segment.text

            translated.append(
                TranslatedSegment(
                    start=segment.start,
                    end=segment.end,
                    original_text=segment.text,
                    translated_text=translated_text,
                )
            )

        return translated

    def translate_text(self, text: str) -> str:
        """Translate a single text from Indonesian to English with chess term pre-processing."""
        try:
            # Pre-process: replace chess terms with placeholders
            processed_text = self._apply_chess_terms(text)

            # Translate
            if self._use_gcp:
                result = self._google_cloud_translate(processed_text)
            else:
                result = self._deep_translate(processed_text)

            # Post-process: replace placeholders with English chess terms
            for placeholder, english_term in self._placeholder_to_english.items():
                result = result.replace(placeholder, english_term)
                result = result.replace(placeholder.lower(), english_term)
                result = result.replace(placeholder.capitalize(), english_term)

            # Add punctuation for natural TTS prosody
            result = self._add_punctuation(result)

            return result
        except TranslationError:
            raise
        except Exception as e:
            raise TranslationError(f"Failed to translate text: {e}") from e

    def _google_cloud_translate(self, text: str) -> str:
        """Translate using Google Cloud Translation API v2 with API key."""
        payload = json.dumps({
            "q": text,
            "source": "id",
            "target": "en",
            "format": "text",
        }).encode("utf-8")

        url = f"{_GOOGLE_TRANSLATE_URL}?key={self.api_key}"
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        try:
            with urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace") if e.fp else str(e)
            raise TranslationError(
                f"Google Translate API error ({e.code}): {error_body[:200]}"
            ) from e
        except (URLError, TimeoutError) as e:
            raise TranslationError(f"Google Translate API connection error: {e}") from e

        try:
            translations = result["data"]["translations"]
            return translations[0]["translatedText"]
        except (KeyError, IndexError) as e:
            raise TranslationError(f"Unexpected API response: {e}") from e

    def _deep_translate(self, text: str) -> str:
        """Fallback: translate using deep-translator (free Google Translate)."""
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source="id", target="en")
        return translator.translate(text)

    def _apply_chess_terms(self, text: str) -> str:
        """Replace Indonesian chess terms with unique placeholders before translation."""
        result = text
        for term in self._sorted_terms:
            placeholder = self._term_to_placeholder[term]
            pattern = re.compile(
                r"\b" + re.escape(term) + r"\b", re.IGNORECASE
            )
            result = pattern.sub(placeholder, result)
        return result

    def _add_punctuation(self, text: str) -> str:
        """Add natural punctuation using Gemini AI, with simple fallback.

        Gemini understands context and places commas/periods accurately.
        Falls back to basic rules if Gemini unavailable.
        """
        if not text or not text.strip():
            return text

        if self._use_gemini:
            try:
                return self._gemini_punctuate(text)
            except Exception as e:
                logger.warning("Gemini punctuation failed (%s), using fallback", e)

        return self._simple_punctuate(text)

    def _gemini_punctuate(self, text: str) -> str:
        """Use Gemini to add natural punctuation for TTS."""
        _GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

        prompt = (
            "Add natural punctuation (commas, periods, question marks) to this chess commentary text "
            "for text-to-speech reading. Rules:\n"
            "- Add commas where a speaker would naturally pause\n"
            "- Add periods at sentence boundaries\n"
            "- Do NOT change, add, or remove any words\n"
            "- Return ONLY the punctuated text, nothing else\n\n"
            f"Text: {text}"
        )

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 256,
            },
        }).encode("utf-8")

        url = f"{_GEMINI_URL}?key={self.gemini_api_key}"
        req = Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")

        with urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                punctuated = parts[0].get("text", "").strip()
                # Sanity check: Gemini should not change words significantly
                if punctuated and len(punctuated) < len(text) * 2:
                    return punctuated

        return self._simple_punctuate(text)

    @staticmethod
    def _simple_punctuate(text: str) -> str:
        """Simple fallback: just ensure text ends with a period."""
        result = text.strip()
        if result and result[-1] not in '.!?':
            result += '.'
        return result
