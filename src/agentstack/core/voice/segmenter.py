"""UtteranceSegmenter — state machine that turns a stream of VAD verdicts
into discrete utterances.

Feed it 32 ms (512 sample @ 16 kHz Int16) PCM frames one at a time. While the
user is speaking we accumulate. When we see `silence_frames` consecutive
silence frames (default 800 ms ≈ 25 frames), we emit the accumulated PCM as
one utterance and reset.

Two guards:
- `min_utterance_ms` drops bursts of background noise that briefly cross the
  VAD threshold.
- `max_utterance_ms` force-emits a long monologue so an open mic doesn't grow
  the buffer without bound.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentstack.core.voice.vad import FRAME_BYTES, FRAME_MS, SileroVAD


@dataclass
class SegmenterConfig:
    silence_ms: int = 800
    min_utterance_ms: int = 250
    max_utterance_ms: int = 30_000


class UtteranceSegmenter:
    def __init__(self, vad: SileroVAD | None = None, config: SegmenterConfig | None = None) -> None:
        self.vad = vad or SileroVAD()
        self.cfg = config or SegmenterConfig()
        self._buf = bytearray()
        self._silence_frames = 0
        self._speech_frames = 0
        self._silence_threshold = max(1, self.cfg.silence_ms // FRAME_MS)
        self._min_speech_frames = max(1, self.cfg.min_utterance_ms // FRAME_MS)
        self._max_total_frames = max(1, self.cfg.max_utterance_ms // FRAME_MS)

    def reset(self) -> None:
        self._buf.clear()
        self._silence_frames = 0
        self._speech_frames = 0

    @property
    def is_recording(self) -> bool:
        """True between the first detected speech frame and utterance close.
        Lets the WS route detect "speech just started" by sampling the value
        before and after each feed()."""
        return self._speech_frames > 0

    def feed(self, frame: bytes) -> bytes | None:
        """Feed one VAD-sized frame. Returns the utterance PCM bytes when one closes."""
        if len(frame) != FRAME_BYTES:
            raise ValueError(f"expected {FRAME_BYTES} bytes per frame (got {len(frame)})")

        is_speech = self.vad.is_speech(frame)
        if is_speech:
            self._silence_frames = 0
            self._speech_frames += 1
            self._buf.extend(frame)
        elif self._speech_frames > 0:
            # In-utterance silence: keep accumulating so the audio stays continuous
            # for Whisper, but count toward the close threshold.
            self._silence_frames += 1
            self._buf.extend(frame)

        # Force-close on max length even if user is still speaking.
        if len(self._buf) // FRAME_BYTES >= self._max_total_frames:
            return self._emit()

        if (
            self._speech_frames >= self._min_speech_frames
            and self._silence_frames >= self._silence_threshold
        ):
            return self._emit()

        return None

    def _emit(self) -> bytes | None:
        if self._speech_frames < self._min_speech_frames:
            self.reset()
            return None
        utterance = bytes(self._buf)
        self.reset()
        return utterance
