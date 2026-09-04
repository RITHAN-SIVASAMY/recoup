"""Synthesize real, playable audio for the demo video's voice-call beat
(docs/07-DEMO-SCRIPT.md, 3:05-3:35). `make demo` never generates real TTS --
run_call() explicitly documents itself as "the offline/scripted path (cut
line)", using plain text turns for speed and determinism. This script uses
the real production TTS engine (voice/tts.py, same hi-IN-MadhurNeural voice
a real call would use) to render one actual case's real, already-captured
transcript into an .mp3 -- not a placeholder script, the real conversation
that produced a real ptp.captured event.

Usage:
    uv run python scripts/synthesize_demo_call.py
    (writes data/demo_call.mp3 -- the system's side of case
    01M1P9HYQQCK90M76ZB3R17GZX's real 6-turn call, which captured a real
    promise to pay 499.00 by 2026-01-10, confidence 0.92)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from recoup.voice.tts import synthesize

# The real system-side lines from case 01M1P9HYQQCK90M76ZB3R17GZX's actual
# 6-turn call, pulled directly from its voice.turn events -- not written for
# this script.
_SYSTEM_LINES = [
    "Namaste! Main Acme ki taraf se baat kar raha hoon.",
    "Main ek automated assistant hoon, Acme ke liye kaam karta hoon. "
    "Aap kisi bhi time 'stop' bol kar opt-out kar sakte hain, "
    "ya 'human' bol kar kisi insaan se baat kar sakte hain.",
    "Aapke ek recent payment mein kuch issue aaya tha, uske baare mein baat karni thi.",
    "Kya aap ise abhi resolve karna chahenge, ya koi date bata sakte hain jab aap pay kar payenge?",
    "Theek hai, please bataiye aap kab tak aur kitna pay kar payenge.",
    "Toh confirm kar raha hoon — aap 499 rupees 10 January tak pay karenge. Sahi hai?",
]

_OUT_PATH = Path("data/demo_call.mp3")


async def main() -> None:
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    full_text = " ... ".join(_SYSTEM_LINES)
    await synthesize(full_text, _OUT_PATH)
    print(f"wrote {_OUT_PATH} -- case 01M1P9HYQQCK90M76ZB3R17GZX's real call, system side")
    print("customer side was real ASR input during the call -- not re-synthesizable from")
    print("text alone; narrate over this with the transcript on screen, or read the")
    print("customer lines yourself off docs/07-DEMO-SCRIPT.md's companion transcript.")


if __name__ == "__main__":
    asyncio.run(main())
