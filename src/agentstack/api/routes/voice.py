"""WebSocket voice endpoint.

Wire format:
  - Inbound text frame: JSON. Required first message is the init handshake:
        {"type":"init","jwt":"...","collection_id":"...","conversation_id":"...?"}
  - Inbound binary frame: 1024 bytes Int16 mono PCM @ 16 kHz (one 32 ms VAD frame).
  - Outbound text frame: JSON event ({type: transcript|agent_token|final|error|ready, ...}).
  - Outbound binary frame: a complete WAV blob for one synthesized sentence.

The WS bypasses our HTTP `AuthMiddleware` (different ASGI scope), so the route
authenticates inline by decoding the JWT in the init message.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from agentstack.core.voice.segmenter import SegmenterConfig, UtteranceSegmenter
from agentstack.core.voice.vad import FRAME_BYTES, SAMPLE_RATE
from agentstack.infra.db import get_sessionmaker
from agentstack.infra.logging import get_logger
from agentstack.models.collection import Collection
from agentstack.models.user import User
from agentstack.services import voice_service
from agentstack.services.conversation_service import (
    create_conversation,
    get_conversation_for_user,
)
from agentstack.services.jwt_service import InvalidTokenError, decode_access_token

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


async def _send_json(ws: WebSocket, payload: dict[str, Any]) -> None:
    await ws.send_text(json.dumps(payload))


async def _authenticate(ws: WebSocket) -> tuple[User, Collection, UUID] | None:
    """Wait for the init message and resolve user + collection + conversation.

    Returns (user, collection, conversation_id) on success, or None after
    closing the socket with an appropriate code.
    """
    try:
        raw = await asyncio.wait_for(ws.receive_text(), timeout=10.0)
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="init timeout")
        return None

    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await ws.close(code=status.WS_1003_UNSUPPORTED_DATA, reason="init must be JSON")
        return None

    if msg.get("type") != "init" or "jwt" not in msg or "collection_id" not in msg:
        await ws.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="init missing type/jwt/collection_id",
        )
        return None

    try:
        claims = decode_access_token(msg["jwt"])
    except InvalidTokenError as e:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"jwt: {e}")
        return None

    try:
        collection_id = UUID(msg["collection_id"])
    except (TypeError, ValueError):
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="bad collection_id")
        return None

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        user = await session.get(User, claims.user_id)
        if user is None or not user.is_active:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="user inactive")
            return None

        result = await session.execute(
            select(Collection).where(
                Collection.id == collection_id, Collection.owner_id == user.id
            )
        )
        collection = result.scalar_one_or_none()
        if collection is None:
            await ws.close(
                code=status.WS_1008_POLICY_VIOLATION, reason="collection not found"
            )
            return None

        if msg.get("conversation_id"):
            try:
                conv_uuid = UUID(msg["conversation_id"])
            except (TypeError, ValueError):
                await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="bad conversation_id")
                return None
            conv = await get_conversation_for_user(session, conv_uuid, user.id)
        else:
            conv = await create_conversation(
                session,
                user_id=user.id,
                title="Voice session",
                collection_id=collection_id,
            )

    return user, collection, conv.id


async def _handle_utterance(
    ws: WebSocket,
    *,
    user_id: UUID,
    collection_id: UUID,
    conversation_id: UUID,
    pcm: bytes,
) -> None:
    """Run ASR + the voice turn, forwarding events as they arrive."""
    try:
        transcript = await voice_service.transcribe_utterance(pcm, sample_rate=SAMPLE_RATE)
    except Exception as exc:
        logger.exception("transcription failed")
        await _send_json(ws, {"type": "error", "message": f"asr: {exc}"})
        return

    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        async for event in voice_service.run_voice_turn(
            transcript,
            db=session,
            user_id=user_id,
            conversation_id=conversation_id,
            collection_id=collection_id,
        ):
            if event.type == "audio":
                audio_bytes = event.payload.get("bytes", b"")
                if audio_bytes:
                    await ws.send_bytes(audio_bytes)
            else:
                await _send_json(ws, {"type": event.type, **event.payload})


@router.websocket("/stream")
async def voice_stream(ws: WebSocket) -> None:
    await ws.accept()
    auth = await _authenticate(ws)
    if auth is None:
        return
    user, collection, conversation_id = auth

    await _send_json(
        ws,
        {
            "type": "ready",
            "user_id": str(user.id),
            "collection_id": str(collection.id),
            "conversation_id": str(conversation_id),
            "frame_bytes": FRAME_BYTES,
            "sample_rate": SAMPLE_RATE,
        },
    )

    segmenter = UtteranceSegmenter(config=SegmenterConfig())
    turn_task: asyncio.Task | None = None

    async def _cancel_in_flight(reason: str) -> None:
        nonlocal turn_task
        if turn_task is None or turn_task.done():
            return
        turn_task.cancel()
        try:
            await turn_task
        except (asyncio.CancelledError, Exception):
            pass
        turn_task = None
        await _send_json(ws, {"type": "cancelled", "reason": reason})

    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break

            if "bytes" in msg and msg["bytes"] is not None:
                frame = msg["bytes"]
                if len(frame) != FRAME_BYTES:
                    await _send_json(
                        ws,
                        {
                            "type": "error",
                            "message": f"expected {FRAME_BYTES}-byte frame, got {len(frame)}",
                        },
                    )
                    continue

                was_recording = segmenter.is_recording
                try:
                    utterance = segmenter.feed(frame)
                except Exception as exc:
                    logger.exception("vad/segmenter error")
                    await _send_json(ws, {"type": "error", "message": f"vad: {exc}"})
                    continue

                # Barge-in: speech started during in-flight turn → cancel it.
                if (
                    not was_recording
                    and segmenter.is_recording
                    and turn_task is not None
                    and not turn_task.done()
                ):
                    await _cancel_in_flight("user spoke during playback")

                if utterance and (turn_task is None or turn_task.done()):
                    turn_task = asyncio.create_task(
                        _handle_utterance(
                            ws,
                            user_id=user.id,
                            collection_id=collection.id,
                            conversation_id=conversation_id,
                            pcm=utterance,
                        )
                    )

            elif "text" in msg and msg["text"] is not None:
                try:
                    payload = json.loads(msg["text"])
                except json.JSONDecodeError:
                    continue
                ctrl = payload.get("type")
                if ctrl == "ping":
                    await _send_json(ws, {"type": "pong"})
                elif ctrl == "interrupt":
                    # Client Stop button / barge-in: cancel the in-flight turn so
                    # the server stops generating more TTS, not just local audio.
                    await _cancel_in_flight("client interrupt")

    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("voice ws crashed")
    finally:
        if turn_task and not turn_task.done():
            turn_task.cancel()
