"""Command-line entry points: demo, replay, verify."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from recoup.audit.event_store import create_engine
from recoup.audit.verify import verify_chain, verify_replay_equality
from recoup.demo import run_batch
from recoup.measurement.report import render_headline_block, to_json, to_markdown

app = typer.Typer(add_completion=False, no_args_is_help=True)

_REPORTS_DIR = Path("data/reports")


@app.command()
def demo(seed: int = 42, cases: int = 500) -> None:
    """Run the seeded batch end-to-end and print the headline block."""
    report = asyncio.run(run_batch(seed=seed, n_cases=cases))
    block = render_headline_block(report)
    typer.echo(block)

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    batch_id = report.inputs.batch_id
    (_REPORTS_DIR / f"{batch_id}.json").write_text(to_json(report), encoding="utf-8")
    (_REPORTS_DIR / f"{batch_id}.md").write_text(to_markdown(report), encoding="utf-8")
    typer.echo(f"\nwrote {_REPORTS_DIR / f'{batch_id}.json'} and {_REPORTS_DIR / f'{batch_id}.md'}")

    if not report.significance.significant:
        typer.secho(
            "NOTE: the incremental lift is NOT statistically significant at this batch size "
            f"(p={report.significance.p_value:.4f}); the MDE above is the honest bound.",
            fg=typer.colors.YELLOW,
        )


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
