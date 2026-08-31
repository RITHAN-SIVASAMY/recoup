"""Command-line entry points: demo, replay, verify."""

from __future__ import annotations

import asyncio

import typer

from recoup.audit.event_store import create_engine
from recoup.audit.verify import verify_chain, verify_replay_equality

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def demo(seed: int = 42) -> None:
    """Run the seeded batch end-to-end and print the headline block."""
    typer.secho(
        "recoup demo: not implemented yet - policy (Phase 04), economics (Phase 05) and "
        "measurement (Phase 10) all still have to land before this can print real numbers.",
        fg=typer.colors.RED,
        err=True,
    )
    raise typer.Exit(code=1)


@app.command()
def replay() -> None:
    """Rebuild projections from the event log and compare against the stored ones."""

    async def _run() -> bool:
        engine = create_engine()
        try:
            return await verify_replay_equality(engine)
        finally:
            await engine.dispose()

    matches = asyncio.run(_run())
    if matches:
        typer.echo("recoup replay: rebuilt projections match the stored cases table.")
    else:
        typer.secho(
            "recoup replay: rebuilt projections DIVERGE from the stored cases table.",
            fg=typer.colors.RED,
            err=True,
        )
        raise typer.Exit(code=1)


@app.command()
def verify() -> None:
    """Verify the hash chain and replay equality."""

    async def _run() -> tuple[bool, int, str | None, str | None, bool]:
        engine = create_engine()
        try:
            chain = await verify_chain(engine)
            replay_ok = await verify_replay_equality(engine) if chain.verified else False
            return (
                chain.verified,
                chain.events_checked,
                chain.divergent_event_id,
                chain.reason,
                replay_ok,
            )
        finally:
            await engine.dispose()

    chain_ok, checked, divergent_id, reason, replay_ok = asyncio.run(_run())
    if chain_ok and replay_ok:
        typer.echo(f"AUDIT CHAIN VERIFIED - {checked} events - replay equality PASS")
        return
    if not chain_ok:
        typer.secho(
            f"AUDIT CHAIN BROKEN at event {divergent_id}: {reason}",
            fg=typer.colors.RED,
            err=True,
        )
    else:
        typer.secho(
            "AUDIT CHAIN VERIFIED but replay equality FAILED - "
            "rebuilt projections diverge from the stored cases table.",
            fg=typer.colors.RED,
            err=True,
        )
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
