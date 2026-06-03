"""Silero VAD wrapper.

Silero v5 expects 512-sample chunks at 16 kHz mono Int16 PCM. We expose a
single `is_speech(pcm: bytes) -> bool` so the segmenter doesn't have to care
about torch/onnx details.

Threshold of 0.5 follows the silero defaults. The torch model lazy-loads on
first use and is cached process-local.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

import numpy as np

from agentstack.infra.logging import get_logger

if TYPE_CHECKING:
    import torch

logger = get_logger(__name__)

SAMPLE_RATE = 16_000
FRAME_SAMPLES = 512  # silero v5 requirement
FRAME_MS = (FRAME_SAMPLES * 1000) // SAMPLE_RATE  # 32
FRAME_BYTES = FRAME_SAMPLES * 2  # int16 mono

_SPEECH_THRESHOLD = 0.5


@lru_cache(maxsize=1)
def _load_model():
    import torch  # noqa: F401  (torch import is a side-effect of load)
    from silero_vad import load_silero_vad

    logger.info("loading silero vad")
    return load_silero_vad()


class SileroVAD:
    """Thin stateful VAD. Reset state between sessions by reinstantiating."""

    def __init__(self, threshold: float = _SPEECH_THRESHOLD) -> None:
        import torch

        self._model = _load_model()
        self._torch = torch
        self.threshold = threshold

    def is_speech(self, pcm: bytes) -> bool:
        if len(pcm) != FRAME_BYTES:
            raise ValueError(
                f"expected {FRAME_BYTES} bytes per frame (got {len(pcm)})"
            )
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        tensor = self._torch.from_numpy(samples)
        with self._torch.no_grad():
            prob = float(self._model(tensor, SAMPLE_RATE))
        return prob >= self.threshold
