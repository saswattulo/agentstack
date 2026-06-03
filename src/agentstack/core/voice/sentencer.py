"""SentenceBuffer — turn a stream of LLM token deltas into whole sentences
suitable for sending to TTS.

The qwen3 chat model wraps its reasoning in `<think>...</think>` which we
strip before any boundary detection. Sentence boundary is `.` / `?` / `!`
followed by a space or end-of-input. A hard 200-char cap force-flushes if
the model emits a long run-on (e.g. markdown table).
"""

from __future__ import annotations

import re

_THINK_OPEN = "<think>"
_THINK_CLOSE = "</think>"
_BOUNDARY_RE = re.compile(r'([.!?])(\s+|$)')
_MAX_CHARS = 200


class SentenceBuffer:
    def __init__(self, max_chars: int = _MAX_CHARS) -> None:
        self.max_chars = max_chars
        self._buf = ""
        self._inside_think = False

    def feed(self, token: str) -> list[str]:
        """Append a token; return zero-or-more complete sentences."""
        if not token:
            return []

        cleaned = self._consume(token)
        if not cleaned:
            return []

        self._buf += cleaned
        return self._drain()

    def flush(self) -> str | None:
        """Return any remaining buffered text at end-of-stream (drops `<think>` residue)."""
        leftover = self._buf.strip()
        self._buf = ""
        self._inside_think = False
        return leftover or None

    def _consume(self, token: str) -> str:
        """Strip out any `<think>...</think>` content that spans the buffer + new token."""
        if not (self._inside_think or _THINK_OPEN in token or _THINK_CLOSE in token):
            return token

        text = token
        out_parts: list[str] = []
        while text:
            if self._inside_think:
                idx = text.find(_THINK_CLOSE)
                if idx == -1:
                    return "".join(out_parts)
                text = text[idx + len(_THINK_CLOSE):]
                self._inside_think = False
            else:
                idx = text.find(_THINK_OPEN)
                if idx == -1:
                    out_parts.append(text)
                    return "".join(out_parts)
                out_parts.append(text[:idx])
                text = text[idx + len(_THINK_OPEN):]
                self._inside_think = True
        return "".join(out_parts)

    def _drain(self) -> list[str]:
        sentences: list[str] = []
        while True:
            match = _BOUNDARY_RE.search(self._buf)
            if match:
                end = match.end(1)  # include the punctuation, drop trailing whitespace
                sentence = self._buf[:end].strip()
                self._buf = self._buf[match.end():]
                if sentence:
                    sentences.append(sentence)
                continue
            if len(self._buf) >= self.max_chars:
                # No boundary in sight — flush the prefix to keep TTS moving.
                cut = self._buf.rfind(" ", 0, self.max_chars)
                if cut <= 0:
                    cut = self.max_chars
                sentence = self._buf[:cut].strip()
                self._buf = self._buf[cut:].lstrip()
                if sentence:
                    sentences.append(sentence)
                continue
            break
        return sentences
