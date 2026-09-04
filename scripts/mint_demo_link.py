"""Mint a fresh, valid single-use recovery link for one case — for the demo
video's "customer side" beat only. Never used by the running system itself;
real links are minted at send-time by execution/dispatcher.py off the actual
ladder step. This just lets a presenter open a real, working `/r/<token>`
page on their phone without waiting for a real send to happen live.

Usage:
    uv run python scripts/mint_demo_link.py <case_id> [ladder_step]
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from recoup.execution.links import generate_link_token
from recoup.settings import Settings


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: uv run python scripts/mint_demo_link.py <case_id> [ladder_step]")
        raise SystemExit(1)

    case_id = sys.argv[1]
    ladder_step = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    settings = Settings()

    token = generate_link_token(
        case_id,
        ladder_step,
        secret=settings.link_signing_secret,
        ttl=timedelta(hours=2),
        now=datetime.now(UTC),
    )
    print(f"http://localhost:3000/r/{token}")


if __name__ == "__main__":
    main()
