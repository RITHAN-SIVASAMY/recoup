"""FR-10.2: Hinglish text-to-speech via edge-tts (`hi-IN`/`en-IN` neural
voices, free, no per-call cost). A thin wrapper only — `voice/runtime.py`
never needs to know this is edge-tts specifically; the offline/test call
path (ADR-0006's simulator-first pattern, generalized to voice per the
phase's own cut line: "render the call offline as an audio artifact") never
calls this at all, since a scripted transcript needs no audio synthesized
to prove the graph and guards behave correctly.
"""

from __future__ import annotations

from pathlib import Path

import edge_tts

DEFAULT_VOICE = "hi-IN-MadhurNeural"


async def synthesize(text: str, out_path: Path, *, voice: str = DEFAULT_VOICE) -> Path:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))
    return out_path
