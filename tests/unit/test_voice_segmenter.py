"""UtteranceSegmenter unit tests with a stub VAD."""

import pytest

from agentstack.core.voice.segmenter import SegmenterConfig, UtteranceSegmenter
from agentstack.core.voice.vad import FRAME_BYTES


class StubVAD:
    """Returns canned verdicts in order; raises if asked for more."""

    def __init__(self, verdicts: list[bool]) -> None:
        self.verdicts = list(verdicts)

    def is_speech(self, frame: bytes) -> bool:
        if not self.verdicts:
            raise AssertionError("VAD asked beyond canned verdicts")
        return self.verdicts.pop(0)


FRAME = b"\x00" * FRAME_BYTES


def _drive(seg: UtteranceSegmenter, n: int) -> bytes | None:
    last = None
    for _ in range(n):
        last = seg.feed(FRAME)
        if last is not None:
            break
    return last


@pytest.mark.unit
def test_speech_then_silence_closes_utterance():
    cfg = SegmenterConfig(silence_ms=96, min_utterance_ms=64, max_utterance_ms=10_000)
    # 96ms silence at 32ms/frame = 3 silence frames; min_utterance 64ms = 2 speech frames
    seg = UtteranceSegmenter(
        vad=StubVAD([True, True, True, False, False, False]),
        config=cfg,
    )
    out = _drive(seg, 6)
    assert out is not None
    # 6 frames buffered (3 speech + 3 silence) → 6 * 1024 = 6144 bytes
    assert len(out) == 6 * FRAME_BYTES


@pytest.mark.unit
def test_short_burst_dropped_when_below_min_utterance():
    cfg = SegmenterConfig(silence_ms=64, min_utterance_ms=128, max_utterance_ms=10_000)
    # 1 speech frame (32ms) then 2 silence (64ms) → below min_utterance (4 frames)
    seg = UtteranceSegmenter(
        vad=StubVAD([True, False, False]),
        config=cfg,
    )
    out = _drive(seg, 3)
    assert out is None


@pytest.mark.unit
def test_silence_only_emits_nothing():
    cfg = SegmenterConfig(silence_ms=96, min_utterance_ms=64, max_utterance_ms=10_000)
    seg = UtteranceSegmenter(
        vad=StubVAD([False] * 10),
        config=cfg,
    )
    out = _drive(seg, 10)
    assert out is None


@pytest.mark.unit
def test_max_utterance_force_closes_long_monologue():
    cfg = SegmenterConfig(silence_ms=10_000, min_utterance_ms=32, max_utterance_ms=96)
    # silence_ms huge → only max_ms will trigger close. 96ms = 3 frames @ 32ms.
    seg = UtteranceSegmenter(
        vad=StubVAD([True, True, True, True]),
        config=cfg,
    )
    out = _drive(seg, 4)
    assert out is not None
    assert len(out) == 3 * FRAME_BYTES


@pytest.mark.unit
def test_in_utterance_brief_silence_keeps_buffering():
    """Brief silence between two speech bursts should NOT close the utterance."""
    cfg = SegmenterConfig(silence_ms=160, min_utterance_ms=32, max_utterance_ms=10_000)
    # 160ms silence = 5 frames. We feed 2 silence in the middle (well under).
    seg = UtteranceSegmenter(
        vad=StubVAD([True, True, False, False, True, True, False, False, False, False, False]),
        config=cfg,
    )
    out = _drive(seg, 11)
    assert out is not None
    # buffer accumulates everything from first speech up to close
    assert len(out) == 11 * FRAME_BYTES


@pytest.mark.unit
def test_wrong_frame_size_raises():
    seg = UtteranceSegmenter(vad=StubVAD([True]))
    with pytest.raises(ValueError):
        seg.feed(b"\x00" * (FRAME_BYTES - 1))


@pytest.mark.unit
def test_reset_clears_state():
    cfg = SegmenterConfig(silence_ms=96, min_utterance_ms=32, max_utterance_ms=10_000)
    seg = UtteranceSegmenter(vad=StubVAD([True, True]), config=cfg)
    seg.feed(FRAME)
    seg.feed(FRAME)
    seg.reset()
    assert seg._buf == bytearray()
    assert seg._speech_frames == 0
    assert seg._silence_frames == 0


@pytest.mark.unit
def test_is_recording_tracks_silence_to_speech_transition():
    """The barge-in path samples this property before/after feed() to detect
    a silence→speech edge."""
    seg = UtteranceSegmenter(vad=StubVAD([False, True, True, False, False, False, False]))
    assert seg.is_recording is False  # before any frame

    seg.feed(FRAME)  # silence
    assert seg.is_recording is False

    seg.feed(FRAME)  # first speech frame
    assert seg.is_recording is True

    seg.feed(FRAME)  # more speech
    assert seg.is_recording is True


@pytest.mark.unit
def test_is_recording_resets_after_utterance_emit():
    cfg = SegmenterConfig(silence_ms=96, min_utterance_ms=32, max_utterance_ms=10_000)
    # 1 speech + 3 silence at this config: min=32ms (1 frame), silence=96ms (3 frames)
    seg = UtteranceSegmenter(
        vad=StubVAD([True, False, False, False]),
        config=cfg,
    )
    seg.feed(FRAME)
    assert seg.is_recording is True
    seg.feed(FRAME)
    seg.feed(FRAME)
    out = seg.feed(FRAME)
    assert out is not None
    assert seg.is_recording is False  # reset after emit
