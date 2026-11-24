"""Speech-to-Text (STT) fallback for LLM providers without native audio support."""

import io
from typing import Literal

from openai import AsyncOpenAI

from src.config import Settings

GROQ_OPENAI_BASE_URL = "https://api.groq.com/openai/v1"


class AudioTranscriber:
    """Transcribes in-memory audio buffers using Groq Whisper or OpenAI Whisper."""

    def __init__(
        self,
        provider: Literal["groq", "openai"],
        api_key: str,
    ) -> None:
        self._provider = provider
        if provider == "groq":
            self._client = AsyncOpenAI(api_key=api_key, base_url=GROQ_OPENAI_BASE_URL)
            self._model = "whisper-large-v3-turbo"
        else:
            self._client = AsyncOpenAI(api_key=api_key)
            self._model = "whisper-1"

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
        """Transcribe raw audio bytes from memory without writing to disk."""
        extension = "ogg" if "ogg" in mime_type else "mp3"
        buffer = io.BytesIO(audio_bytes)
        buffer.name = f"voice.{extension}"
        try:
            transcript = await self._client.audio.transcriptions.create(
                model=self._model,
                file=buffer,
                language="pt",
            )
            return transcript.text.strip()
        finally:
            buffer.close()


def create_audio_transcriber(settings: Settings) -> AudioTranscriber | None:
    """Create an AudioTranscriber if STT fallback is configured."""
    if settings.stt_provider == "none" or not settings.stt_api_key:
        return None
    if settings.stt_provider == "auto":
        return AudioTranscriber(provider="groq", api_key=settings.stt_api_key)
    return AudioTranscriber(provider=settings.stt_provider, api_key=settings.stt_api_key)
