"""Piper TTS in-process.

Groq's PlayAI TTS endpoint was decommissioned (ADR-010). We synthesize with
Piper, model `en_US-amy-medium`, loaded once per process. The model is
auto-downloaded to `settings.voice_tts_model_path` on first use if missing,
so a fresh container with the persistent `piper_models` volume bootstraps
itself in ~5s.
"""

from __future__ import annotations

import asyncio
import io
import os
import urllib.request
import wave
from functools import lru_cache
from pathlib import Path

from agentstack.config import settings
from agentstack.infra.logging import get_logger
from agentstack.infra.tracing import (
    INPUT_VALUE,
    OUTPUT_VALUE,
    SPAN_KIND,
    get_tracer,
    set_attrs,
    truncate,
)

logger = get_logger(__name__)

_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/amy/medium"


def _ensure_model() -> str:
    onnx_path = Path(settings.voice_tts_model_path)
    json_path = Path(str(onnx_path) + ".json")

    if onnx_path.exists() and json_path.exists():
        return str(onnx_path)

    onnx_path.parent.mkdir(parents=True, exist_ok=True)
    for name, target in (
        ("en_US-amy-medium.onnx", onnx_path),
        ("en_US-amy-medium.onnx.json", json_path),
    ):
        if target.exists():
            continue
        url = f"{_HF_BASE}/{name}"
        logger.info("downloading piper voice", url=url, target=str(target))
        urllib.request.urlretrieve(url, target)
        logger.info("piper voice ready", target=str(target), bytes=os.path.getsize(target))

    return str(onnx_path)


@lru_cache(maxsize=1)
def _voice():
    from piper import PiperVoice

    model_path = _ensure_model()
    logger.info("loading piper voice", model=model_path)
    return PiperVoice.load(model_path)


def _synthesize_sync(text: str) -> tuple[bytes, int]:
    voice = _voice()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        voice.synthesize_wav(text, w)
    return buf.getvalue(), voice.config.sample_rate


async def synthesize(text: str) -> tuple[bytes, int]:
    """Return (WAV bytes, sample_rate). Runs Piper on a thread to keep the loop free."""
    tracer = get_tracer()
    with tracer.start_as_current_span("tts.piper") as span:
        clean = (text or "").strip()
        set_attrs(
            span,
            **{
                SPAN_KIND: "TOOL",
                "tool.name": "piper.tts",
                "tts.voice": "en_US-amy-medium",
                "text.chars": len(clean),
                INPUT_VALUE: truncate(clean),
            },
        )
        if not clean:
            return b"", 22050
        audio, sr = await asyncio.to_thread(_synthesize_sync, clean)
        set_attrs(
            span,
            **{
                "audio.bytes": len(audio),
                "audio.sample_rate": sr,
                OUTPUT_VALUE: f"wav {len(audio)} bytes @ {sr}Hz",
            },
        )
        return audio, sr
