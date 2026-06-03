"""Voice turn orchestration.

A voice turn = (utterance PCM in) → (ASR text) → (existing query agent) →
(sentence-chunked TTS audio out). We reuse `query_service.stream_query` so
caching, eval, citations, conversation memory and tracing all keep working
without changes — voice is just a different transport for the same query.
"""

from __future__ import annotations

import io
import wave
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from agentstack.core.voice.sentencer import SentenceBuffer
from agentstack.core.voice.tts import synthesize as tts_synthesize
from agentstack.core.voice.vad import SAMPLE_RATE
from agentstack.infra.llm import get_chat_client
from agentstack.infra.logging import get_logger
from agentstack.schemas.query import QueryRequest
from agentstack.services import query_service

logger = get_logger(__name__)


@dataclass
class VoiceEvent:
    type: str  # "transcript" | "agent_token" | "audio" | "final" | "error"
    payload: dict[str, Any]


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Wrap raw Int16 mono PCM in a minimal WAV container for Whisper."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def transcribe_utterance(pcm: bytes, *, sample_rate: int = SAMPLE_RATE) -> str:
    """Run Whisper on a PCM utterance and return the cleaned transcript."""
    wav = pcm_to_wav(pcm, sample_rate=sample_rate)
    text = await get_chat_client().transcribe(wav, language="en")
    return (text or "").strip()


async def run_voice_turn(
    transcript: str,
    *,
    db: AsyncSession,
    user_id: UUID,
    conversation_id: UUID | None,
    collection_id: UUID,
    api_key_id: UUID | None = None,
    top_k: int = 5,
    use_web_search: bool = True,
) -> AsyncIterator[VoiceEvent]:
    """Drive one voice turn end-to-end. Yields VoiceEvents in order:
    transcript → agent_token* (interleaved with audio*) → final | error.
    """
    yield VoiceEvent("transcript", {"text": transcript})

    if not transcript:
        yield VoiceEvent("error", {"message": "empty transcript"})
        return

    request = QueryRequest(
        collection_id=collection_id,
        question=transcript,
        top_k=top_k,
        use_web_search=use_web_search,
        conversation_id=conversation_id,
    )

    sentencer = SentenceBuffer()
    try:
        async for event in query_service.stream_query(
            request,
            db=db,
            user_id=user_id,
            conversation_id=conversation_id,
            api_key_id=api_key_id,
        ):
            etype = event.get("type")
            data = event.get("data", {})

            if etype == "token":
                token = data if isinstance(data, str) else data.get("text", "")
                yield VoiceEvent("agent_token", {"delta": token})
                for sentence in sentencer.feed(token):
                    audio, sr = await tts_synthesize(sentence)
                    if audio:
                        yield VoiceEvent(
                            "audio",
                            {"bytes": audio, "sample_rate": sr, "text": sentence},
                        )

            elif etype == "final":
                # Flush any buffered partial as the closing audio.
                tail = sentencer.flush()
                if tail:
                    audio, sr = await tts_synthesize(tail)
                    if audio:
                        yield VoiceEvent(
                            "audio",
                            {"bytes": audio, "sample_rate": sr, "text": tail},
                        )
                payload = data if isinstance(data, dict) else {}
                yield VoiceEvent("final", payload)
                return

            elif etype == "error":
                msg = data if isinstance(data, str) else data.get("error", "unknown")
                yield VoiceEvent("error", {"message": msg})
                return

            # tool_start / tool_end pass through silently — the UI cares about
            # transcript, tokens, audio, and final only.

    except Exception as exc:
        logger.exception("voice turn failed")
        yield VoiceEvent("error", {"message": f"{exc.__class__.__name__}: {exc}"})
