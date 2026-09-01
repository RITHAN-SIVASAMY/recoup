"""FR-10 (implicit): speech-to-text via faster-whisper, local, CPU, no
per-minute cost. A thin wrapper — the model is loaded lazily and only on
first real use, so importing this module never triggers a model download.
Same offline-first caveat as `voice/tts.py`: the test/demo call path never
calls this, since transcripts are already text there.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

DEFAULT_MODEL_SIZE = "small"


@dataclass(frozen=True)
class Transcription:
    text: str
    confidence: float


@lru_cache
def _model(model_size: str = DEFAULT_MODEL_SIZE) -> WhisperModel:
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(audio_path: Path, *, model_size: str = DEFAULT_MODEL_SIZE) -> Transcription:
    segments, _info = _model(model_size).transcribe(str(audio_path))
    pieces = list(segments)
    text = " ".join(segment.text.strip() for segment in pieces).strip()
    if not pieces:
        return Transcription(text="", confidence=0.0)
    # faster-whisper reports per-segment avg_logprob, not a 0-1 confidence;
    # a standard, documented approximation is exp(avg_logprob), clamped.
    avg_logprob = sum(segment.avg_logprob for segment in pieces) / len(pieces)
    confidence = max(0.0, min(1.0, 2.718281828**avg_logprob))
    return Transcription(text=text, confidence=confidence)
