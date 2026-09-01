"""SEC-DATA-04: HMAC-signed, single-use, expiring, non-enumerable recovery
links. Pure signing/verification — no I/O, callable with no event loop;
"single-use" (has this exact token already been redeemed) is a separate,
durable concern handled by `LinkRedemptionStore` below, since that requires
a database.

The token embeds no PII — only `case_id` (a ULID, not tied to a phone number
or name) and `ladder_step`. Forging or guessing a token requires the HMAC
secret; guessing a *valid case's* token requires guessing a 128-bit ULID,
same as any other case reference in this system.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from recoup.execution.schema import LinkRedemptionRow

_SIGNATURE_LENGTH = 32


@dataclass(frozen=True)
class LinkPayload:
    case_id: str
    ladder_step: int
    expires_at: datetime


def _sign(secret: str, payload_bytes: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()[
        :_SIGNATURE_LENGTH
    ]


def generate_link_token(
    case_id: str, ladder_step: int, *, secret: str, ttl: timedelta, now: datetime
) -> str:
    expires_at = now + ttl
    payload = f"{case_id}:{ladder_step}:{int(expires_at.timestamp())}".encode()
    payload_b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    return f"{payload_b64}.{_sign(secret, payload)}"


def verify_link_token(token: str, *, secret: str, now: datetime) -> LinkPayload | None:
    try:
        payload_b64, signature = token.split(".", 1)
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(padded)
        case_id, ladder_step_str, expires_epoch_str = payload_bytes.decode("ascii").split(":")
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None

    if not hmac.compare_digest(signature, _sign(secret, payload_bytes)):
        return None

    expires_at = datetime.fromtimestamp(int(expires_epoch_str), tz=now.tzinfo or None)
    if now >= expires_at:
        return None
    return LinkPayload(case_id=case_id, ladder_step=int(ladder_step_str), expires_at=expires_at)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class LinkRedemptionStore:
    """Durable single-use enforcement: a token may be redeemed — for a
    state-changing action (paid, opted out, remind-later set) — exactly
    once. Merely viewing the page does not redeem the link."""

    def __init__(self, engine: AsyncEngine) -> None:
        self._sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def is_redeemed(self, token: str) -> bool:
        async with self._sessionmaker() as session:
            row = await session.get(LinkRedemptionRow, _token_hash(token))
            return row is not None

    async def redeem(self, token: str, *, case_id: str, action: str, now: datetime) -> bool:
        """Returns True if this call performed the redemption, False if the
        token was already redeemed (by this or a concurrent request)."""
        async with self._sessionmaker() as session, session.begin():
            token_hash = _token_hash(token)
            existing = await session.get(LinkRedemptionRow, token_hash)
            if existing is not None:
                return False
            session.add(
                LinkRedemptionRow(
                    token_hash=token_hash, case_id=case_id, action=action, redeemed_at=now
                )
            )
            return True

    async def redemptions_for(self, case_id: str) -> Sequence[LinkRedemptionRow]:
        async with self._sessionmaker() as session:
            rows = await session.scalars(
                select(LinkRedemptionRow).where(LinkRedemptionRow.case_id == case_id)
            )
            return list(rows)
