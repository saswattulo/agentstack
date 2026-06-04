"""End-to-end voice WebSocket test.

Generates a real spoken-audio sample of a known question via Piper, ships
it through the live WS as 32ms PCM frames, and asserts the agent's
transcript + tokens + final-with-citations make it back. Skipped if the
API isn't reachable.
"""

from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import struct
import wave

import httpx
import numpy as np
import pytest
import websockets

API_URL = os.environ.get("AGENTSTACK_API_URL", "http://127.0.0.1:8000")


def _api_up() -> bool:
    try:
        return httpx.get(f"{API_URL}/health", timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _api_up(), reason="API not reachable")


SMALL_DOC = (
    "# Tiny Fixture\n\n"
    "AgentStack uses Qdrant as the vector store.\n\n"
    "Embeddings come from BAAI/bge-small-en-v1.5.\n"
)
QUESTION = "What vector store does AgentStack use?"


def _resample_22050_to_16000(samples: np.ndarray) -> np.ndarray:
    """Trivial linear resample. Good enough for ASR — not high fidelity."""
    src_len = len(samples)
    dst_len = int(src_len * 16000 / 22050)
    src_idx = np.linspace(0, src_len - 1, dst_len)
    return np.interp(src_idx, np.arange(src_len), samples).astype(np.int16)


def _piper_speech_to_pcm16k(text: str) -> bytes:
    """Synthesize via Piper and downsample to 16kHz mono Int16."""
    from agentstack.core.voice.tts import _voice

    voice = _voice()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        voice.synthesize_wav(text, w)
    buf.seek(0)
    with wave.open(buf, "rb") as r:
        src_sr = r.getframerate()
        raw = r.readframes(r.getnframes())
    samples = np.frombuffer(raw, dtype=np.int16)
    if src_sr != 16000:
        samples = _resample_22050_to_16000(samples)
    # 1.5s of trailing silence so VAD definitely fires the close
    # (default silence threshold is 800ms; we double it).
    silence = np.zeros(int(16000 * 1.5), dtype=np.int16)
    return np.concatenate([samples, silence]).tobytes()


def _frames_512(pcm: bytes):
    frame_bytes = 512 * 2
    for i in range(0, len(pcm) - frame_bytes + 1, frame_bytes):
        yield pcm[i : i + frame_bytes]


def _email() -> str:
    return f"voice-{secrets.token_hex(6)}@example.com"


@pytest.mark.integration
@pytest.mark.slow
async def test_voice_ws_full_roundtrip(tmp_path):
    fixture = tmp_path / "tiny.md"
    fixture.write_text(SMALL_DOC, encoding="utf-8")

    async with httpx.AsyncClient(base_url=API_URL, timeout=180) as client:
        token = (
            await client.post(
                "/api/v1/auth/register",
                json={"email": _email(), "password": "voice-test-1234"},
            )
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        coll_id = (
            await client.post(
                "/api/v1/collections",
                json={"name": "voice-tiny", "description": "voice e2e"},
                headers=headers,
            )
        ).json()["id"]

        try:
            with fixture.open("rb") as fh:
                doc_id = (
                    await client.post(
                        f"/api/v1/collections/{coll_id}/ingest",
                        files={"file": ("tiny.md", fh, "text/markdown")},
                        headers=headers,
                    )
                ).json()["id"]
            for _ in range(60):
                status = (
                    await client.get(f"/api/v1/documents/{doc_id}", headers=headers)
                ).json().get("status")
                if status in {"completed", "failed"}:
                    break
                await asyncio.sleep(1)
            assert status == "completed"

            pcm = _piper_speech_to_pcm16k(QUESTION)
            ws_url = API_URL.replace("http", "ws") + "/api/v1/voice/stream"

            transcript = ""
            agent_tokens: list[str] = []
            final: dict | None = None
            error: dict | None = None
            audio_chunks = 0

            async with websockets.connect(ws_url) as ws:
                await ws.send(
                    json.dumps(
                        {"type": "init", "jwt": token, "collection_id": coll_id}
                    )
                )
                ready = json.loads(await asyncio.wait_for(ws.recv(), 10))
                assert ready["type"] == "ready"
                assert ready["frame_bytes"] == 1024

                async def reader():
                    nonlocal transcript, final, error, audio_chunks
                    try:
                        while True:
                            msg = await asyncio.wait_for(ws.recv(), timeout=90)
                            if isinstance(msg, bytes):
                                audio_chunks += 1
                                continue
                            ev = json.loads(msg)
                            if ev["type"] == "transcript":
                                transcript = ev.get("text", "")
                            elif ev["type"] == "agent_token":
                                agent_tokens.append(ev.get("delta", ""))
                            elif ev["type"] == "final":
                                final = ev
                                return
                            elif ev["type"] == "error":
                                error = ev
                                return
                    except asyncio.TimeoutError:
                        return

                read_task = asyncio.create_task(reader())
                for frame in _frames_512(pcm):
                    await ws.send(frame)
                    await asyncio.sleep(0.001)
                await read_task

            assert error is None, f"voice ws error: {error}"
            assert "vector" in transcript.lower() or "qdrant" in transcript.lower(), (
                f"ASR didn't pick up speech: {transcript!r}"
            )
            assert len(agent_tokens) > 0
            assert final is not None
            assert "Qdrant" in "".join(agent_tokens) or "Qdrant" in (
                final.get("answer") or ""
            )
            assert audio_chunks >= 1
        finally:
            await client.delete(f"/api/v1/collections/{coll_id}", headers=headers)
