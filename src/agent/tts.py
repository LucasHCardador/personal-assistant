"""In-memory Text-to-Speech (TTS) synthesis using Microsoft Edge Neural voices."""

import html
import io
import re

import edge_tts

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"
    "\U00002600-\U000027bf"
    "\U0001fa00-\U0001faff"
    "]+",
    flags=re.UNICODE,
)
_WHITESPACE_RE = re.compile(r"\s+")


def html_to_speech_text(raw_text: str) -> str:
    """Convert Telegram HTML messages into clean, natural plain text for TTS."""
    no_tags = _HTML_TAG_RE.sub(" ", raw_text)
    unescaped = html.unescape(no_tags)
    no_emojis = _EMOJI_RE.sub(" ", unescaped)
    cleaned = no_emojis.replace("•", ". ")
    return _WHITESPACE_RE.sub(" ", cleaned).strip()


class SpeechSynthesizer:
    """Synthesizes speech audio strictly in memory without writing files to disk."""

    def __init__(self, voice: str = "pt-BR-AntonioNeural") -> None:
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        """Generate MP3 audio bytes from text in RAM."""
        clean_text = html_to_speech_text(text)
        if not clean_text:
            raise ValueError("Cannot synthesize empty text.")

        communicate = edge_tts.Communicate(clean_text, self._voice)
        buffer = io.BytesIO()
        try:
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    data = chunk.get("data")
                    if isinstance(data, (bytes, bytearray)):
                        buffer.write(data)
            return buffer.getvalue()
        finally:
            buffer.close()
